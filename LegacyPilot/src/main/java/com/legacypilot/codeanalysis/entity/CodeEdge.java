package com.legacypilot.codeanalysis.entity;

import java.util.List;

/**
 * Normalized graph edge produced by parser modules.
 */
public record CodeEdge(
        String edgeId,
        String sourceNodeId,
        String targetNodeId,
        String type,
        double confidence,
        List<EvidenceRef> evidenceRefs
) {
}
