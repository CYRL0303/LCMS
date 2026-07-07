package com.legacypilot.codeanalysis.service;

import com.legacypilot.codeanalysis.dto.CodeTracePath;
import com.legacypilot.codeanalysis.dto.EndpointTraceResult;
import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Queue;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.NOT_FOUND;

@Service
public class EndpointTraceService {
    private static final int DEFAULT_MAX_DEPTH = 6;

    private final CodeAnalysisResultStore codeAnalysisResultStore;

    public EndpointTraceService(CodeAnalysisResultStore codeAnalysisResultStore) {
        this.codeAnalysisResultStore = codeAnalysisResultStore;
    }

    public EndpointTraceResult traceEndpoint(String repoId, String endpointId, String httpMethod, String path, Integer maxDepth) {
        CodeAnalysisResult result = codeAnalysisResultStore.get(repoId);
        CodeEndpoint endpoint = resolveEndpoint(result, endpointId, httpMethod, path);
        int safeMaxDepth = normalizeMaxDepth(maxDepth);

        Map<String, CodeNode> nodesById = new LinkedHashMap<>();
        result.nodes().forEach(node -> nodesById.put(node.nodeId(), node));

        Map<String, List<CodeEdge>> traceEdgesBySource = new LinkedHashMap<>();
        for (CodeEdge edge : result.edges()) {
            if (isTraceEdge(edge)) {
                traceEdgesBySource.computeIfAbsent(edge.sourceNodeId(), ignored -> new ArrayList<>()).add(edge);
            }
        }

        Map<String, CodeNode> matchedNodes = new LinkedHashMap<>();
        Map<String, CodeEdge> matchedEdges = new LinkedHashMap<>();
        Map<String, EvidenceRef> evidenceRefs = new LinkedHashMap<>();
        List<CodeTracePath> graphPaths = new ArrayList<>();

        addEndpointNode(endpoint, nodesById, matchedNodes, evidenceRefs);
        for (CodeEdge handlerEdge : handlerEdges(result, endpoint.endpointId())) {
            addEdge(handlerEdge, matchedEdges, evidenceRefs);
            addNode(handlerEdge.sourceNodeId(), nodesById, matchedNodes, evidenceRefs);
            addNode(handlerEdge.targetNodeId(), nodesById, matchedNodes, evidenceRefs);
            graphPaths.add(new CodeTracePath(
                    List.of(endpoint.endpointId(), handlerEdge.sourceNodeId()),
                    List.of(handlerEdge.edgeId())
            ));
            traceCalls(handlerEdge.sourceNodeId(), safeMaxDepth, traceEdgesBySource, nodesById,
                    matchedNodes, matchedEdges, evidenceRefs, graphPaths);
        }

        return new EndpointTraceResult(
                repoId,
                endpoint,
                List.copyOf(graphPaths),
                List.copyOf(matchedNodes.values()),
                List.copyOf(matchedEdges.values()),
                List.copyOf(evidenceRefs.values())
        );
    }

    private CodeEndpoint resolveEndpoint(CodeAnalysisResult result, String endpointId, String httpMethod, String path) {
        if (endpointId != null && !endpointId.isBlank()) {
            return result.endpoints().stream()
                    .filter(endpoint -> endpoint.endpointId().equals(endpointId))
                    .findFirst()
                    .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Endpoint not found: " + endpointId));
        }
        if (path == null || path.isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "endpointId or path is required.");
        }
        String normalizedMethod = httpMethod == null || httpMethod.isBlank() ? null : httpMethod.trim().toUpperCase();
        return result.endpoints().stream()
                .filter(endpoint -> endpoint.path().equals(path))
                .filter(endpoint -> normalizedMethod == null || endpoint.httpMethod().equalsIgnoreCase(normalizedMethod))
                .findFirst()
                .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Endpoint not found: " + path));
    }

    private int normalizeMaxDepth(Integer maxDepth) {
        if (maxDepth == null) {
            return DEFAULT_MAX_DEPTH;
        }
        if (maxDepth < 1) {
            throw new ResponseStatusException(BAD_REQUEST, "maxDepth must be greater than 0.");
        }
        return Math.min(maxDepth, 20);
    }

    private List<CodeEdge> handlerEdges(CodeAnalysisResult result, String endpointNodeId) {
        return result.edges().stream()
                .filter(edge -> "MAPS_TO_ENDPOINT".equals(edge.type()))
                .filter(edge -> edge.targetNodeId().equals(endpointNodeId))
                .toList();
    }

    private void traceCalls(
            String handlerNodeId,
            int maxDepth,
            Map<String, List<CodeEdge>> traceEdgesBySource,
            Map<String, CodeNode> nodesById,
            Map<String, CodeNode> matchedNodes,
            Map<String, CodeEdge> matchedEdges,
            Map<String, EvidenceRef> evidenceRefs,
            List<CodeTracePath> graphPaths
    ) {
        Queue<TraceState> queue = new ArrayDeque<>();
        queue.add(new TraceState(handlerNodeId, List.of(handlerNodeId), List.of(), 0));
        Set<String> visitedEdges = new HashSet<>();

        while (!queue.isEmpty()) {
            TraceState current = queue.remove();
            if (current.depth() >= maxDepth) {
                continue;
            }
            for (CodeEdge edge : traceEdgesBySource.getOrDefault(current.nodeId(), List.of())) {
                if (!visitedEdges.add(edge.edgeId())) {
                    continue;
                }
                addEdge(edge, matchedEdges, evidenceRefs);
                addNode(edge.sourceNodeId(), nodesById, matchedNodes, evidenceRefs);
                addNode(edge.targetNodeId(), nodesById, matchedNodes, evidenceRefs);

                List<String> nextNodeIds = append(current.nodeIds(), edge.targetNodeId());
                List<String> nextEdgeIds = append(current.edgeIds(), edge.edgeId());
                graphPaths.add(new CodeTracePath(nextNodeIds, nextEdgeIds));
                queue.add(new TraceState(edge.targetNodeId(), nextNodeIds, nextEdgeIds, current.depth() + 1));
            }
        }
    }

    private void addEndpointNode(
            CodeEndpoint endpoint,
            Map<String, CodeNode> nodesById,
            Map<String, CodeNode> matchedNodes,
            Map<String, EvidenceRef> evidenceRefs
    ) {
        addNode(endpoint.endpointId(), nodesById, matchedNodes, evidenceRefs);
        endpoint.evidenceRefs().forEach(evidence -> evidenceRefs.putIfAbsent(evidence.evidenceId(), evidence));
    }

    private void addNode(
            String nodeId,
            Map<String, CodeNode> nodesById,
            Map<String, CodeNode> matchedNodes,
            Map<String, EvidenceRef> evidenceRefs
    ) {
        CodeNode node = nodesById.get(nodeId);
        if (node == null) {
            return;
        }
        matchedNodes.putIfAbsent(node.nodeId(), node);
        node.evidenceRefs().stream()
                .filter(Objects::nonNull)
                .forEach(evidence -> evidenceRefs.putIfAbsent(evidence.evidenceId(), evidence));
    }

    private void addEdge(CodeEdge edge, Map<String, CodeEdge> matchedEdges, Map<String, EvidenceRef> evidenceRefs) {
        matchedEdges.putIfAbsent(edge.edgeId(), edge);
        edge.evidenceRefs().stream()
                .filter(Objects::nonNull)
                .forEach(evidence -> evidenceRefs.putIfAbsent(evidence.evidenceId(), evidence));
    }

    private boolean isTraceEdge(CodeEdge edge) {
        return "CALLS".equals(edge.type()) || "EXECUTES_SQL".equals(edge.type());
    }

    private <T> List<T> append(List<T> values, T value) {
        List<T> copy = new ArrayList<>(values);
        copy.add(value);
        return List.copyOf(copy);
    }

    private record TraceState(String nodeId, List<String> nodeIds, List<String> edgeIds, int depth) {
    }
}
