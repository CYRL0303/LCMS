package com.legacypilot.agent.service;

/**
 * User request handled by the LegacyPilot agent.
 */
public record AgentRequest(
        String message,
        String endpointPath
) {
}
