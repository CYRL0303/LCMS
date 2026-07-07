package com.legacypilot.agenttool.trace.dto;

import com.legacypilot.codeanalysis.dto.CodeTracePath;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.util.List;

/**
 * Agent-facing trace result for one endpoint.
 */
public record EndpointTraceToolResult(
        String repoId,
        CodeEndpoint endpoint,
        List<CodeTracePath> graphPaths,
        List<CodeNode> matchedNodes,
        List<CodeEdge> matchedEdges,
        List<EvidenceRef> evidenceRefs
) {
}
