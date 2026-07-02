package com.legacypilot.agenttool.graph.dto;

import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.CodeGraphSummary;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.util.List;

/**
 * Response DTO for exposing the current code graph to agent tools.
 */
public record CodeGraphResult(
        CodeGraphSummary summary,
        List<CodeEndpoint> endpoints,
        List<CodeNode> nodes,
        List<CodeEdge> edges,
        List<EvidenceRef> evidenceRefs
) {
    public static CodeGraphResult from(CodeAnalysisResult result) {
        return new CodeGraphResult(
                result.summary(),
                result.endpoints(),
                result.nodes(),
                result.edges(),
                result.evidenceRefs()
        );
    }
}
