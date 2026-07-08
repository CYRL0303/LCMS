from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]


def test_graph_visualizer_component_exposes_interactive_layered_surface():
    source = (ROOT / "frontend" / "src" / "GraphVisualizer.tsx").read_text(
        encoding="utf-8"
    )

    assert "function GraphVisualizer" in source
    assert 'data-testid="graph-visualizer"' in source
    assert "graph-layer-overview" in source
    assert "graph-layer-evidence" in source
    assert "graph-layer-paths" in source
    assert "graph-layer-raw" in source
    assert "addEventListener(\"wheel\"" in source
    assert "onPointerDown={handleCanvasPointerDown}" in source
    assert "handleNodePointerDown" in source


def test_graph_visualizer_uses_force_cluster_layout_and_real_fit():
    source = (ROOT / "frontend" / "src" / "GraphVisualizer.tsx").read_text(
        encoding="utf-8"
    )
    package_json = json.loads(
        (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )

    assert "d3-force" in package_json["dependencies"]
    assert "forceSimulation" in source
    assert "forceLink" in source
    assert "forceManyBody" in source
    assert "forceCollide" in source
    assert "clusteredForceLayout" in source
    assert "fitGraphToCanvas" in source
    assert "nodeBounds" in source
    assert "layoutMode" in source


def test_graph_visualizer_exposes_zoom_and_reset_controls():
    source = (ROOT / "frontend" / "src" / "GraphVisualizer.tsx").read_text(
        encoding="utf-8"
    )

    assert "graph-zoom-in" in source
    assert "graph-zoom-out" in source
    assert "graph-fit" in source
    assert "graph-reset" in source
    assert "zoomBy(" in source
    assert "resetLayout" in source


def test_graph_visualizer_defaults_to_evidence_focus_after_bundle_arrives():
    source = (ROOT / "frontend" / "src" / "GraphVisualizer.tsx").read_text(
        encoding="utf-8"
    )

    assert "hasUserSelectedLayer" in source
    assert 'setLayer("evidence")' in source

def test_frontend_loads_full_snapshot_for_existing_graph_selection():
    source = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "loadGraphSnapshotFor" in source
    assert (
        "/v1/graphs/${encodeURIComponent(repoId)}/${encodeURIComponent(graphId)}"
        in source
    )
    assert "<GraphVisualizer" in source


def test_graph_visualizer_styles_are_present():
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

    assert ".graph-visualizer" in styles
    assert ".graph-canvas" in styles
    assert ".graph-layer-button" in styles
def test_graph_viewport_controls_do_not_block_evidence_auto_focus():
    source = (ROOT / "frontend" / "src" / "GraphVisualizer.tsx").read_text(
        encoding="utf-8"
    )

    reset_body = source.split("function resetLayout", 1)[1].split(
        "function fitCurrentView", 1
    )[0]
    fit_body = source.split("function fitCurrentView", 1)[1].split(
        "function zoomBy", 1
    )[0]

    assert "setHasUserSelectedLayer(true)" not in reset_body
    assert "setHasUserSelectedLayer(true)" not in fit_body

def test_frontend_auto_loads_first_persisted_graph_on_empty_startup():
    source = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "hasAutoLoadedStoredGraph" in source
    assert "autoLoadStoredGraph" in source
    assert "storedGraphs[0]" in source
    assert "loadGraphSnapshotFor(firstGraph.repo_id, firstGraph.graph_id)" in source

def test_graph_wheel_zoom_blocks_outer_pipeline_scroll():
    source = (ROOT / "frontend" / "src" / "GraphVisualizer.tsx").read_text(
        encoding="utf-8"
    )

    assert "addEventListener(\"wheel\"" in source
    assert "passive: false" in source
    assert "event.preventDefault()" in source
    assert "event.stopPropagation()" in source


def test_graph_visualizer_has_expanded_modal_view():
    source = (ROOT / "frontend" / "src" / "GraphVisualizer.tsx").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "Maximize2" in source
    assert "graph-expand" in source
    assert "graph-expanded-modal" in source
    assert "graph-modal-backdrop" in source
    assert "graph-modal-canvas" in source
    assert ".graph-modal-backdrop" in styles
    assert "backdrop-filter" in styles

def test_incident_path_does_not_fallback_to_generic_graph_without_evidence():
    source = (ROOT / "frontend" / "src" / "GraphVisualizer.tsx").read_text(
        encoding="utf-8"
    )

    assert "emptyReason" in source
    assert "Build evidence first to render incident path." in source
    assert "incident path pending" in source
    assert "layer === \"paths\" && pathIds.size === 0 && focusIds.size === 0" in source
