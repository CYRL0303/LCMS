package com.legacypilot.agent.catalog;

/**
 * Stable metadata for a tool the agent can call or reference.
 */
public record AgentToolDefinition(
        String name,
        String description,
        boolean implemented
) {
}
