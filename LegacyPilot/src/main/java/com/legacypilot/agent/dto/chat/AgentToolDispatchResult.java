package com.legacypilot.agent.dto.chat;

import com.legacypilot.agent.catalog.AgentToolResult;
import com.legacypilot.agent.dto.rca.RcaInvestigationResult;
import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import java.util.List;

/**
 * Result produced by the rule-based agent tool dispatcher.
 */
public record AgentToolDispatchResult(
        String repoId,
        QueryUnderstandingResult query,
        List<AgentToolResult> toolResults,
        String agentContextText,
        RcaInvestigationResult investigation
) {
}
