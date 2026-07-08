import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";
import type { SimulationLinkDatum, SimulationNodeDatum } from "d3-force";
import { Maximize2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Edge, EvidenceBundle, GraphSnapshot, Node } from "./contracts";

type GraphLayer = "overview" | "evidence" | "paths" | "raw";

type Point = {
  x: number;
  y: number;
};

type Viewport = {
  x: number;
  y: number;
  scale: number;
};

type VisualNode = {
  id: string;
  node: Node;
  x: number;
  y: number;
  degree: number;
  focus: boolean;
  path: boolean;
  group: string;
};

type VisualEdge = {
  id: string;
  edge: Edge;
  source: string;
  target: string;
  focus: boolean;
};

type GraphView = {
  nodes: VisualNode[];
  edges: VisualEdge[];
  omittedNodes: number;
  omittedEdges: number;
  focusCount: number;
  layoutMode: string;
  emptyReason?: string;
};

type LayoutNode = SimulationNodeDatum & {
  id: string;
  node: Node;
  degree: number;
  focus: boolean;
  path: boolean;
  group: string;
};

type LayoutLink = SimulationLinkDatum<LayoutNode>;

type DragState =
  | {
      type: "pan";
      pointerId: number;
      start: Point;
      origin: Point;
    }
  | {
      type: "node";
      pointerId: number;
      nodeId: string;
      offset: Point;
    };

const layers: { key: GraphLayer; label: string; detail: string }[] = [
  { key: "overview", label: "Overview", detail: "Clustered core graph" },
  { key: "evidence", label: "Evidence Focus", detail: "Matched evidence plus neighbors" },
  { key: "paths", label: "Incident Path", detail: "RCA graph paths" },
  { key: "raw", label: "Raw Snapshot", detail: "Clustered snapshot" },
];

const defaultViewport: Viewport = { x: 36, y: 30, scale: 0.9 };
const fitPadding = 36;

export function GraphVisualizer({
  snapshot,
  bundle,
}: {
  snapshot: GraphSnapshot | null;
  bundle: EvidenceBundle | null;
}) {
  const mainSvgRef = useRef<SVGSVGElement | null>(null);
  const modalSvgRef = useRef<SVGSVGElement | null>(null);
  const [layer, setLayer] = useState<GraphLayer>("overview");
  const [hasUserSelectedLayer, setHasUserSelectedLayer] = useState(false);
  const [viewport, setViewport] = useState<Viewport>(defaultViewport);
  const [positions, setPositions] = useState<Record<string, Point>>({});
  const [drag, setDrag] = useState<DragState | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const graphView = useMemo(
    () => buildGraphView(snapshot, bundle, layer),
    [snapshot, bundle, layer],
  );
  const viewKey = `${snapshot?.graph_id || "none"}:${layer}:${graphView.layoutMode}:${graphView.nodes
    .map((node) => node.id)
    .join("|")}`;

  useEffect(() => {
    setHasUserSelectedLayer(false);
    setLayer("overview");
  }, [snapshot?.graph_id]);

  useEffect(() => {
    if (bundle && !hasUserSelectedLayer && layer !== "evidence") {
      setLayer("evidence");
    }
  }, [bundle, hasUserSelectedLayer, layer]);

  useEffect(() => {
    resetLayout();
  }, [viewKey]);
  useEffect(() => {
    if (!isExpanded) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsExpanded(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    window.requestAnimationFrame(() => fitToView());
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isExpanded]);
  useEffect(() => {
    const handleNativeWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      zoomAt(event.clientX, event.clientY, event.deltaY > 0 ? 0.88 : 1.12);
    };
    const svgElements = [mainSvgRef.current, modalSvgRef.current].filter(
      (svg): svg is SVGSVGElement => svg !== null,
    );
    for (const svg of svgElements) {
      svg.addEventListener("wheel", handleNativeWheel, { passive: false });
    }
    return () => {
      for (const svg of svgElements) {
        svg.removeEventListener("wheel", handleNativeWheel);
      }
    };
  }, [isExpanded, viewport.scale, viewport.x, viewport.y]);

  if (!snapshot) {
    return (
      <div className="summary-block graph-visualizer" data-testid="graph-visualizer">
        <div className="graph-header">
          <div>
            <h3>Graph Visualizer</h3>
            <p className="meta-line">Index repo or select existing graph to render nodes.</p>
          </div>
        </div>
      </div>
    );
  }

  const nodeCount = graphView.nodes.length;
  const edgeCount = graphView.edges.length;

  function initialPositions(): Record<string, Point> {
    const next: Record<string, Point> = {};
    for (const node of graphView.nodes) {
      next[node.id] = { x: node.x, y: node.y };
    }
    return next;
  }
  function activeSvg(): SVGSVGElement | null {
    return isExpanded ? modalSvgRef.current || mainSvgRef.current : mainSvgRef.current;
  }

  function pointFromClient(clientX: number, clientY: number): Point {
    const rect = activeSvg()?.getBoundingClientRect();
    if (!rect) {
      return { x: 0, y: 0 };
    }
    return {
      x: (clientX - rect.left - viewport.x) / viewport.scale,
      y: (clientY - rect.top - viewport.y) / viewport.scale,
    };
  }

  function fitToView(nextPositions: Record<string, Point> = positions) {
    const rect = activeSvg()?.getBoundingClientRect();
    if (!rect || graphView.nodes.length === 0) {
      setViewport(defaultViewport);
      return;
    }
    setViewport(fitGraphToCanvas(graphView.nodes, nextPositions, rect.width, rect.height));
  }

  function resetLayout() {
    const next = initialPositions();
    setPositions(next);
    window.requestAnimationFrame(() => fitToView(next));
  }

  function fitCurrentView() {
    fitToView();
  }

  function zoomAt(clientX: number, clientY: number, multiplier: number) {
    const rect = activeSvg()?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    const before = pointFromClient(clientX, clientY);
    const nextScale = clamp(viewport.scale * multiplier, 0.06, 3.6);
    setViewport({
      x: clientX - rect.left - before.x * nextScale,
      y: clientY - rect.top - before.y * nextScale,
      scale: nextScale,
    });
  }

  function zoomBy(multiplier: number) {
    const rect = activeSvg()?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, multiplier);
  }
  function handleCanvasPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if ((event.target as Element).closest("[data-graph-node]")) {
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({
      type: "pan",
      pointerId: event.pointerId,
      start: { x: event.clientX, y: event.clientY },
      origin: { x: viewport.x, y: viewport.y },
    });
  }

  function handleNodePointerDown(
    event: React.PointerEvent<SVGGElement>,
    nodeId: string,
  ) {
    event.stopPropagation();
    activeSvg()?.setPointerCapture(event.pointerId);
    const graphPoint = pointFromClient(event.clientX, event.clientY);
    const current = positions[nodeId] || { x: 0, y: 0 };
    setDrag({
      type: "node",
      pointerId: event.pointerId,
      nodeId,
      offset: {
        x: graphPoint.x - current.x,
        y: graphPoint.y - current.y,
      },
    });
  }

  function handlePointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }
    if (drag.type === "pan") {
      setViewport({
        ...viewport,
        x: drag.origin.x + event.clientX - drag.start.x,
        y: drag.origin.y + event.clientY - drag.start.y,
      });
      return;
    }
    const graphPoint = pointFromClient(event.clientX, event.clientY);
    setPositions((current) => ({
      ...current,
      [drag.nodeId]: {
        x: graphPoint.x - drag.offset.x,
        y: graphPoint.y - drag.offset.y,
      },
    }));
  }

  function handlePointerUp(event: React.PointerEvent<SVGSVGElement>) {
    if (drag?.pointerId === event.pointerId) {
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // Pointer capture may already be released by browser.
      }
      setDrag(null);
    }
  }

  function selectLayer(nextLayer: GraphLayer) {
    setHasUserSelectedLayer(true);
    setLayer(nextLayer);
  }

  return (
    <>
      <div className="summary-block graph-visualizer" data-testid="graph-visualizer">
      <div className="graph-header">
        <div>
          <h3>Graph Visualizer</h3>
          <p className="meta-line">
            {snapshot.repo_id} / {snapshot.graph_id}
          </p>
        </div>
        <div className="graph-view-controls" aria-label="Graph viewport controls">
          <button
            aria-label="Zoom out"
            className="icon-button secondary graph-control-button"
            data-testid="graph-zoom-out"
            onClick={() => zoomBy(0.82)}
            type="button"
          >
            -
          </button>
          <button
            aria-label="Zoom in"
            className="icon-button secondary graph-control-button"
            data-testid="graph-zoom-in"
            onClick={() => zoomBy(1.18)}
            type="button"
          >
            +
          </button>
          <button
            className="icon-button secondary graph-fit-button"
            data-testid="graph-fit"
            onClick={fitCurrentView}
            type="button"
          >
            Fit
          </button>
          <button
            aria-label="Expand graph"
            className="icon-button secondary graph-control-button"
            data-testid="graph-expand"
            onClick={() => setIsExpanded(true)}
            type="button"
          >
            <Maximize2 aria-hidden="true" />
          </button>
          <button
            className="icon-button secondary graph-fit-button"
            data-testid="graph-reset"
            onClick={() => resetLayout()}
            type="button"
          >
            Reset
          </button>
        </div>
      </div>

      <div className="graph-layer-controls" aria-label="Graph visual layers">
        {layers.map((item) => (
          <button
            aria-pressed={layer === item.key}
            className={`graph-layer-button ${layer === item.key ? "active" : ""}`}
            data-testid={
              item.key === "overview"
                ? "graph-layer-overview"
                : item.key === "evidence"
                  ? "graph-layer-evidence"
                  : item.key === "paths"
                    ? "graph-layer-paths"
                    : "graph-layer-raw"
            }
            key={item.key}
            onClick={() => selectLayer(item.key)}
            type="button"
          >
            <strong>{item.label}</strong>
            <span>{item.detail}</span>
          </button>
        ))}
      </div>

      <div className="graph-stats">
        <span>{nodeCount} rendered nodes</span>
        <span>{edgeCount} rendered edges</span>
        <span>{graphView.focusCount} focus nodes</span>
        <span>{graphView.layoutMode}</span>
        {(graphView.omittedNodes > 0 || graphView.omittedEdges > 0) && (
          <span>
            omitted {graphView.omittedNodes} nodes / {graphView.omittedEdges} edges
          </span>
        )}
      </div>

      {graphView.emptyReason && (
        <div className="graph-empty-message" data-testid="graph-empty-message">
          {graphView.emptyReason}
        </div>
      )}

      <svg
        aria-label="Interactive code graph"
        className="graph-canvas"
        data-testid="graph-canvas"
        onPointerDown={handleCanvasPointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        ref={mainSvgRef}
        role="img"
      >
        <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`}>
          <g className="graph-edges">
            {graphView.edges.map((edge) => {
              const source = positions[edge.source];
              const target = positions[edge.target];
              if (!source || !target) {
                return null;
              }
              return (
                <line
                  className={edge.focus ? "graph-edge focus" : "graph-edge"}
                  key={edge.id}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                >
                  <title>{edge.edge.type}</title>
                </line>
              );
            })}
          </g>
          <g className="graph-nodes">
            {graphView.nodes.map((node) => {
              const position = positions[node.id] || { x: node.x, y: node.y };
              const radius = nodeRadius(node);
              return (
                <g
                  className={`graph-node ${node.focus ? "focus" : ""} ${
                    node.path ? "path" : ""
                  }`}
                  data-graph-node="true"
                  key={node.id}
                  onPointerDown={(event) => handleNodePointerDown(event, node.id)}
                  transform={`translate(${position.x} ${position.y})`}
                >
                  <circle
                    fill={nodeColor(node.node.type)}
                    r={radius}
                    stroke={node.path ? "#f59e0b" : node.focus ? "#12633f" : "#344054"}
                  />
                  <text dx={radius + 7} dy="4">
                    {shortLabel(node.node)}
                  </text>
                  <title>
                    {node.node.type}: {node.node.qualified_name || node.node.name}
                  </title>
                </g>
              );
            })}
          </g>
        </g>
      </svg>
      </div>

      {isExpanded && (
        <div
          className="graph-modal-backdrop"
          data-testid="graph-modal-backdrop"
          onClick={() => setIsExpanded(false)}
        >
          <section
            aria-label="Expanded graph viewer"
            className="graph-modal"
            data-testid="graph-expanded-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="graph-modal-header">
              <div>
                <h3>Graph Visualizer</h3>
                <p className="meta-line">
                  {snapshot.repo_id} / {snapshot.graph_id}
                </p>
              </div>
              <div className="graph-view-controls" aria-label="Expanded graph viewport controls">
                <button
                  aria-label="Zoom out"
                  className="icon-button secondary graph-control-button"
                  data-testid="graph-modal-zoom-out"
                  onClick={() => zoomBy(0.82)}
                  type="button"
                >
                  -
                </button>
                <button
                  aria-label="Zoom in"
                  className="icon-button secondary graph-control-button"
                  data-testid="graph-modal-zoom-in"
                  onClick={() => zoomBy(1.18)}
                  type="button"
                >
                  +
                </button>
                <button
                  className="icon-button secondary graph-fit-button"
                  data-testid="graph-modal-fit"
                  onClick={fitCurrentView}
                  type="button"
                >
                  Fit
                </button>
                <button
                  className="icon-button secondary graph-fit-button"
                  data-testid="graph-modal-reset"
                  onClick={() => resetLayout()}
                  type="button"
                >
                  Reset
                </button>
                <button
                  aria-label="Close expanded graph"
                  className="icon-button secondary graph-control-button"
                  data-testid="graph-modal-close"
                  onClick={() => setIsExpanded(false)}
                  type="button"
                >
                  <X aria-hidden="true" />
                </button>
              </div>
            </div>

            <div className="graph-layer-controls graph-modal-layers" aria-label="Expanded graph visual layers">
              {layers.map((item) => (
                <button
                  aria-pressed={layer === item.key}
                  className={`graph-layer-button ${layer === item.key ? "active" : ""}`}
                  data-testid={`graph-modal-layer-${item.key}`}
                  key={item.key}
                  onClick={() => selectLayer(item.key)}
                  type="button"
                >
                  <strong>{item.label}</strong>
                  <span>{item.detail}</span>
                </button>
              ))}
            </div>

            <div className="graph-stats">
              <span>{nodeCount} rendered nodes</span>
              <span>{edgeCount} rendered edges</span>
              <span>{graphView.focusCount} focus nodes</span>
              <span>{graphView.layoutMode}</span>
              {(graphView.omittedNodes > 0 || graphView.omittedEdges > 0) && (
                <span>
                  omitted {graphView.omittedNodes} nodes / {graphView.omittedEdges} edges
                </span>
              )}
            </div>

            {graphView.emptyReason && (
              <div className="graph-empty-message" data-testid="graph-modal-empty-message">
                {graphView.emptyReason}
              </div>
            )}

            <svg
              aria-label="Expanded interactive code graph"
              className="graph-canvas graph-canvas-expanded"
              data-testid="graph-modal-canvas"
              onPointerDown={handleCanvasPointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
                    ref={modalSvgRef}
              role="img"
            >
              <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`}>
                <g className="graph-edges">
                  {graphView.edges.map((edge) => {
                    const source = positions[edge.source];
                    const target = positions[edge.target];
                    if (!source || !target) {
                      return null;
                    }
                    return (
                      <line
                        className={edge.focus ? "graph-edge focus" : "graph-edge"}
                        key={`modal-${edge.id}`}
                        x1={source.x}
                        y1={source.y}
                        x2={target.x}
                        y2={target.y}
                      >
                        <title>{edge.edge.type}</title>
                      </line>
                    );
                  })}
                </g>
                <g className="graph-nodes">
                  {graphView.nodes.map((node) => {
                    const position = positions[node.id] || { x: node.x, y: node.y };
                    const radius = nodeRadius(node);
                    return (
                      <g
                        className={`graph-node ${node.focus ? "focus" : ""} ${
                          node.path ? "path" : ""
                        }`}
                        data-graph-node="true"
                        key={`modal-${node.id}`}
                        onPointerDown={(event) => handleNodePointerDown(event, node.id)}
                        transform={`translate(${position.x} ${position.y})`}
                      >
                        <circle
                          fill={nodeColor(node.node.type)}
                          r={radius}
                          stroke={node.path ? "#f59e0b" : node.focus ? "#12633f" : "#344054"}
                        />
                        <text dx={radius + 7} dy="4">
                          {shortLabel(node.node)}
                        </text>
                        <title>
                          {node.node.type}: {node.node.qualified_name || node.node.name}
                        </title>
                      </g>
                    );
                  })}
                </g>
              </g>
            </svg>
          </section>
        </div>
      )}
    </>
  );
}

function buildGraphView(
  snapshot: GraphSnapshot | null,
  bundle: EvidenceBundle | null,
  layer: GraphLayer,
): GraphView {
  if (!snapshot) {
    return {
      nodes: [],
      edges: [],
      omittedNodes: 0,
      omittedEdges: 0,
      focusCount: 0,
      layoutMode: "force cluster",
    };
  }
  const degree = nodeDegrees(snapshot.edges);
  const focusIds = collectFocusNodeIds(snapshot, bundle);
  const pathIds = collectPathNodeIds(snapshot, bundle);
  if (layer === "paths" && pathIds.size === 0 && focusIds.size === 0) {
    return {
      nodes: [],
      edges: [],
      omittedNodes: 0,
      omittedEdges: 0,
      focusCount: 0,
      layoutMode: "incident path pending",
      emptyReason: "Build evidence first to render incident path.",
    };
  }
  const rankedNodes = [...snapshot.nodes].sort((left, right) => {
    const leftFocus = Number(focusIds.has(left.node_id) || pathIds.has(left.node_id));
    const rightFocus = Number(focusIds.has(right.node_id) || pathIds.has(right.node_id));
    if (leftFocus !== rightFocus) {
      return rightFocus - leftFocus;
    }
    const degreeDelta = (degree.get(right.node_id) || 0) - (degree.get(left.node_id) || 0);
    if (degreeDelta !== 0) {
      return degreeDelta;
    }
    return left.node_id.localeCompare(right.node_id);
  });

  let selectedIds: Set<string>;
  let nodeLimit: number;
  let edgeLimit: number;
  let layoutMode: string;

  if (layer === "raw") {
    nodeLimit = 500;
    edgeLimit = 900;
    layoutMode = "raw force cluster";
    selectedIds = new Set(snapshot.nodes.slice(0, nodeLimit).map((node) => node.node_id));
  } else if (layer === "paths") {
    nodeLimit = 100;
    edgeLimit = 180;
    layoutMode = "incident path cluster";
    selectedIds = new Set(pathIds.size > 0 ? pathIds : focusIds);
    expandWithNeighbors(selectedIds, snapshot.edges, 1);
  } else if (layer === "evidence") {
    nodeLimit = 140;
    edgeLimit = 240;
    layoutMode = "evidence force cluster";
    selectedIds = new Set(focusIds);
    expandWithNeighbors(selectedIds, snapshot.edges, 1);
  } else {
    nodeLimit = 96;
    edgeLimit = 160;
    layoutMode = "overview force cluster";
    selectedIds = new Set(rankedNodes.slice(0, nodeLimit).map((node) => node.node_id));
  }

  if (selectedIds.size === 0) {
    selectedIds = new Set(rankedNodes.slice(0, nodeLimit).map((node) => node.node_id));
  }

  const selectedNodes = rankedNodes
    .filter((node) => selectedIds.has(node.node_id))
    .slice(0, nodeLimit);
  const visibleIds = new Set(selectedNodes.map((node) => node.node_id));
  const selectedEdges = snapshot.edges
    .filter(
      (edge) =>
        visibleIds.has(edge.source_node_id) && visibleIds.has(edge.target_node_id),
    )
    .slice(0, edgeLimit);

  const laidOut = clusteredForceLayout(
    selectedNodes,
    selectedEdges,
    degree,
    focusIds,
    pathIds,
    layer,
  );
  return {
    nodes: laidOut,
    edges: selectedEdges.map((edge) => ({
      id: edge.edge_id,
      edge,
      source: edge.source_node_id,
      target: edge.target_node_id,
      focus:
        focusIds.has(edge.source_node_id) ||
        focusIds.has(edge.target_node_id) ||
        pathIds.has(edge.source_node_id) ||
        pathIds.has(edge.target_node_id),
    })),
    omittedNodes: Math.max(0, snapshot.nodes.length - selectedNodes.length),
    omittedEdges: Math.max(0, snapshot.edges.length - selectedEdges.length),
    focusCount: focusIds.size,
    layoutMode,
  };
}

function clusteredForceLayout(
  nodes: Node[],
  edges: Edge[],
  degree: Map<string, number>,
  focusIds: Set<string>,
  pathIds: Set<string>,
  layer: GraphLayer,
): VisualNode[] {
  const groups = [...new Set(nodes.map((node) => nodeGroup(node.type)))].sort(
    (left, right) => groupRank(left) - groupRank(right),
  );
  const centers = clusterCenters(groups, layer);
  const groupCounters = new Map<string, number>();
  const layoutNodes: LayoutNode[] = nodes.map((node, index) => {
    const group = nodeGroup(node.type);
    const count = groupCounters.get(group) || 0;
    groupCounters.set(group, count + 1);
    const center = centers.get(group) || { x: 420, y: 260 };
    const angle = count * 2.399963229728653;
    const spread = 28 + Math.sqrt(count + 1) * 18;
    return {
      id: node.node_id,
      node,
      degree: degree.get(node.node_id) || 0,
      focus: focusIds.has(node.node_id),
      path: pathIds.has(node.node_id),
      group,
      x: center.x + Math.cos(angle) * spread,
      y: center.y + Math.sin(angle) * spread,
    };
  });
  const visibleIds = new Set(layoutNodes.map((node) => node.id));
  const layoutLinks: LayoutLink[] = edges
    .filter(
      (edge) => visibleIds.has(edge.source_node_id) && visibleIds.has(edge.target_node_id),
    )
    .map((edge) => ({ source: edge.source_node_id, target: edge.target_node_id }));

  const simulation = forceSimulation<LayoutNode>(layoutNodes)
    .force(
      "link",
      forceLink<LayoutNode, LayoutLink>(layoutLinks)
        .id((node) => node.id)
        .distance((link) => edgeDistance(link, layer))
        .strength(layer === "raw" ? 0.12 : 0.24),
    )
    .force("charge", forceManyBody<LayoutNode>().strength(layer === "raw" ? -210 : -280))
    .force(
      "collide",
      forceCollide<LayoutNode>()
        .radius((node) => nodeRadius(node) + labelWidth(node.node) + 8)
        .strength(0.85),
    )
    .force(
      "x",
      forceX<LayoutNode>((node) => centers.get(node.group)?.x || 420).strength(
        layer === "overview" ? 0.12 : 0.16,
      ),
    )
    .force(
      "y",
      forceY<LayoutNode>((node) => centers.get(node.group)?.y || 260).strength(
        layer === "overview" ? 0.12 : 0.16,
      ),
    )
    .stop();

  for (let tick = 0; tick < 260; tick += 1) {
    simulation.tick();
  }

  return layoutNodes.map((node) => ({
    id: node.id,
    node: node.node,
    x: node.x || 0,
    y: node.y || 0,
    degree: node.degree,
    focus: node.focus,
    path: node.path,
    group: node.group,
  }));
}

function clusterCenters(groups: string[], layer: GraphLayer): Map<string, Point> {
  const width = layer === "raw" ? 1180 : 940;
  const height = layer === "raw" ? 720 : 600;
  const columns = Math.min(4, Math.max(1, groups.length));
  const rows = Math.ceil(groups.length / columns);
  const centers = new Map<string, Point>();
  groups.forEach((group, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const x = columns === 1 ? width / 2 : 120 + (column * (width - 240)) / (columns - 1);
    const y = rows === 1 ? height / 2 : 110 + (row * (height - 220)) / Math.max(1, rows - 1);
    centers.set(group, { x, y });
  });
  return centers;
}

function fitGraphToCanvas(
  nodes: VisualNode[],
  positions: Record<string, Point>,
  canvasWidth: number,
  canvasHeight: number,
): Viewport {
  const bounds = nodeBounds(nodes, positions);
  if (!bounds) {
    return defaultViewport;
  }
  const graphWidth = Math.max(1, bounds.maxX - bounds.minX);
  const graphHeight = Math.max(1, bounds.maxY - bounds.minY);
  const scale = clamp(
    Math.min(
      (canvasWidth - fitPadding * 2) / graphWidth,
      (canvasHeight - fitPadding * 2) / graphHeight,
    ),
     0.06,
    1.45,
  );
  return {
    x: (canvasWidth - graphWidth * scale) / 2 - bounds.minX * scale,
    y: (canvasHeight - graphHeight * scale) / 2 - bounds.minY * scale,
    scale,
  };
}

function nodeBounds(
  nodes: VisualNode[],
  positions: Record<string, Point>,
): { minX: number; maxX: number; minY: number; maxY: number } | null {
  if (nodes.length === 0) {
    return null;
  }
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const node of nodes) {
    const point = positions[node.id] || { x: node.x, y: node.y };
    const radius = nodeRadius(node);
    const label = labelWidth(node.node);
    minX = Math.min(minX, point.x - radius - 8);
    maxX = Math.max(maxX, point.x + radius + label + 18);
    minY = Math.min(minY, point.y - radius - 12);
    maxY = Math.max(maxY, point.y + radius + 12);
  }
  return { minX, maxX, minY, maxY };
}

function edgeDistance(link: LayoutLink, layer: GraphLayer): number {
  const sourceGroup = layoutLinkGroup(link.source);
  const targetGroup = layoutLinkGroup(link.target);
  if (sourceGroup && targetGroup && sourceGroup === targetGroup) {
    return layer === "raw" ? 58 : 72;
  }
  return layer === "raw" ? 140 : 165;
}

function layoutLinkGroup(value: string | number | LayoutNode | undefined): string | null {
  if (!value || typeof value === "string" || typeof value === "number") {
    return null;
  }
  return value.group;
}

function nodeDegrees(edges: Edge[]): Map<string, number> {
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source_node_id, (degree.get(edge.source_node_id) || 0) + 1);
    degree.set(edge.target_node_id, (degree.get(edge.target_node_id) || 0) + 1);
  }
  return degree;
}

function collectFocusNodeIds(
  snapshot: GraphSnapshot,
  bundle: EvidenceBundle | null,
): Set<string> {
  const ids = new Set<string>();
  if (!bundle) {
    return ids;
  }
  for (const node of bundle.matched_nodes) {
    ids.add(node.node_id);
  }
  const lookup = tokenLookup(snapshot.nodes);
  for (const evidence of [
    ...bundle.code_evidence,
    ...bundle.sql_evidence,
    ...bundle.config_evidence,
    ...bundle.log_evidence,
  ]) {
    if (!evidence.file_path) {
      continue;
    }
    for (const node of snapshot.nodes) {
      if (node.source_location?.file_path === evidence.file_path) {
        ids.add(node.node_id);
      }
    }
  }
  for (const part of bundle.graph_paths.flat()) {
    const id = lookup.get(normalizeToken(part));
    if (id) {
      ids.add(id);
    }
  }
  return ids;
}

function collectPathNodeIds(
  snapshot: GraphSnapshot,
  bundle: EvidenceBundle | null,
): Set<string> {
  const ids = new Set<string>();
  if (!bundle) {
    return ids;
  }
  const lookup = tokenLookup(snapshot.nodes);
  for (const part of bundle.graph_paths.flat()) {
    const id = lookup.get(normalizeToken(part));
    if (id) {
      ids.add(id);
    }
  }
  return ids;
}

function tokenLookup(nodes: Node[]): Map<string, string> {
  const lookup = new Map<string, string>();
  for (const node of nodes) {
    for (const value of [
      node.node_id,
      node.name,
      node.qualified_name || "",
      node.qualified_name?.split(".").slice(-2).join(".") || "",
    ]) {
      const token = normalizeToken(value);
      if (token && !lookup.has(token)) {
        lookup.set(token, node.node_id);
      }
    }
  }
  return lookup;
}

function expandWithNeighbors(ids: Set<string>, edges: Edge[], depth: number) {
  for (let round = 0; round < depth; round += 1) {
    const next = new Set(ids);
    for (const edge of edges) {
      if (ids.has(edge.source_node_id)) {
        next.add(edge.target_node_id);
      }
      if (ids.has(edge.target_node_id)) {
        next.add(edge.source_node_id);
      }
    }
    ids.clear();
    for (const id of next) {
      ids.add(id);
    }
  }
}

function nodeGroup(type: string): string {
  const value = type.toLowerCase();
  if (value.includes("api") || value.includes("route")) return "API";
  if (value.includes("controller")) return "Controller";
  if (value.includes("service")) return "Service";
  if (value.includes("mapper")) return "Mapper";
  if (value.includes("sql")) return "SQL";
  if (value.includes("table")) return "Table";
  if (value.includes("config")) return "Config";
  if (value.includes("exception")) return "Exception";
  if (value.includes("method")) return "Method";
  if (value.includes("class")) return "Class";
  return "Other";
}

function groupRank(group: string): number {
  const order = [
    "API",
    "Controller",
    "Service",
    "Method",
    "Mapper",
    "SQL",
    "Table",
    "Config",
    "Exception",
    "Class",
    "Other",
  ];
  const index = order.indexOf(group);
  return index === -1 ? order.length : index;
}

function nodeColor(type: string): string {
  const group = nodeGroup(type);
  if (group === "API") return "#2c7c90";
  if (group === "Controller") return "#176b5c";
  if (group === "Service") return "#4f46e5";
  if (group === "Method") return "#475467";
  if (group === "Mapper") return "#7c3aed";
  if (group === "SQL") return "#b54708";
  if (group === "Table") return "#0f766e";
  if (group === "Config") return "#9a3412";
  if (group === "Exception") return "#b42318";
  if (group === "Class") return "#344054";
  return "#667085";
}

function shortLabel(node: Node): string {
  const value = node.qualified_name || node.name || node.node_id;
  if (value.length <= 36) {
    return value;
  }
  return `${value.slice(0, 16)}...${value.slice(-15)}`;
}

function labelWidth(node: Node): number {
  return Math.min(190, Math.max(46, shortLabel(node).length * 6.3));
}

function nodeRadius(node: Pick<VisualNode, "degree" | "focus" | "path">): number {
  return 9 + Math.min(8, node.degree * 1.15) + (node.focus || node.path ? 2 : 0);
}

function normalizeToken(value: string): string {
  return value.trim().toLowerCase();
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}


