package com.legacypilot.agent.tool;

/**
 * Captured result from one tool call.
 */
public record AgentToolResult(
        String toolName,
        Object payload
) {
}
