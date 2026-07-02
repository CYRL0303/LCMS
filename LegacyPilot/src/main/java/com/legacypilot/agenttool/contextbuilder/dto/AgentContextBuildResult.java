package com.legacypilot.agenttool.contextbuilder.dto;

import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import java.util.List;

/**
 * Structured and text context prepared for the future agent/LLM layer.
 */
public record AgentContextBuildResult(
        String repoId,
        String question,
        QueryUnderstandingResult query,
        List<AgentEndpointContextItem> endpointContexts,
        String agentContextText
) {
}
