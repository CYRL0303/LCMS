package com.legacypilot.agent.service;

import com.legacypilot.agent.tool.AgentToolDefinition;
import com.legacypilot.agent.tool.AgentToolResult;
import java.util.List;

/**
 * Agent answer with the tool context used to produce it.
 */
public record AgentResponse(
        String repoId,
        String answer,
        List<AgentToolDefinition> availableTools,
        List<AgentToolResult> toolResults
) {
}
