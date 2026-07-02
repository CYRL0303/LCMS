package com.legacypilot.agent.model;

import com.legacypilot.agent.tool.AgentToolDefinition;
import com.legacypilot.agent.tool.AgentToolResult;
import java.util.List;

/**
 * Prompt context sent to the model layer.
 */
public record AgentModelRequest(
        String repoId,
        String userMessage,
        List<AgentToolDefinition> availableTools,
        List<AgentToolResult> toolResults
) {
}
