package com.legacypilot.codeanalysis.dto;

import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.util.List;

public record EndpointTraceResult(
        String repoId,
        CodeEndpoint endpoint,
        List<CodeTracePath> graphPaths,
        List<CodeNode> matchedNodes,
        List<CodeEdge> matchedEdges,
        List<EvidenceRef> evidenceRefs
) {
}
