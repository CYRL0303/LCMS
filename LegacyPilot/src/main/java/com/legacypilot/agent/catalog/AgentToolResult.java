package com.legacypilot.agent.catalog;

/**
 * One tool result captured during an agent run.
 */
public record AgentToolResult(
        String toolName,
        Object payload
) {
}
