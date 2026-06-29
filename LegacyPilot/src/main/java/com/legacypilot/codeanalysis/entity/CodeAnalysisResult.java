package com.legacypilot.codeanalysis.entity;

import java.util.List;

/**
 * Complete result of one local Java/Spring analysis run.
 */
public record CodeAnalysisResult(
        CodeGraphSummary summary,
        List<CodeEndpoint> endpoints,
        List<CodeNode> nodes,
        List<CodeEdge> edges,
        List<EvidenceRef> evidenceRefs
) {
}
