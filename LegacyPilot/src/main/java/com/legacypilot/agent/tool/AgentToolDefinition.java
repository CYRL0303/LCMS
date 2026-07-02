package com.legacypilot.agent.tool;

/**
 * Public description of a tool the agent may use.
 */
public record AgentToolDefinition(
        String name,
        String description,
        boolean implemented
) {
}
