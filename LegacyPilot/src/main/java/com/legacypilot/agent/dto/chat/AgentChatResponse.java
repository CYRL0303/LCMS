package com.legacypilot.agent.dto.chat;

import com.legacypilot.agent.catalog.AgentToolDefinition;
import com.legacypilot.agent.catalog.AgentToolResult;
import com.legacypilot.agent.dto.rca.RcaInvestigationResult;
import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import java.util.List;

/**
 * Agent response with the tool context used to produce it.
 */
public record AgentChatResponse(
        String repoId,
        String answer,
        QueryUnderstandingResult query,
        List<AgentToolDefinition> availableTools,
        List<AgentToolResult> toolResults,
        String agentContextText,
        RcaInvestigationResult investigation
) {
}
