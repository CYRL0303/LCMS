package com.legacypilot.lcms.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

/**
 * Minimal Java representation of the Python GraphSnapshot response.
 *
 * Nodes and edges are intentionally kept as maps for the first integration
 * step. Once the frontend graph contract stabilizes, these can become typed
 * DTOs.
 */
public record CodeKnowledgeGraphSnapshotResponse(
        @JsonProperty("graph_id")
        String graphId,

        @JsonProperty("repo_id")
        String repoId,

        List<Map<String, Object>> nodes,

        List<Map<String, Object>> edges,

        @JsonProperty("evidence_refs")
        List<Map<String, Object>> evidenceRefs,

        @JsonProperty("generated_at")
        String generatedAt
) {
    /**
     * Convenience count for controller/service responses that do not need the
     * full graph payload.
     */
    public int nodeCount() {
        return nodes == null ? 0 : nodes.size();
    }

    /**
     * Convenience count for controller/service responses that do not need the
     * full graph payload.
     */
    public int edgeCount() {
        return edges == null ? 0 : edges.size();
    }
}
