package com.legacypilot.agent.model;

import com.legacypilot.agent.catalog.AgentToolDefinition;
import com.legacypilot.agent.catalog.AgentToolResult;
import java.util.List;

/**
 * Context sent from the agent orchestrator to the model layer.
 */
public record AgentModelRequest(
        String repoId,
        String userMessage,
        String agentContextText,
        List<AgentToolDefinition> availableTools,
        List<AgentToolResult> toolResults
) {
}
