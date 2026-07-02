package com.legacypilot.agent.dto.chat;

/**
 * Request DTO for the experimental agent chat endpoint.
 */
public record AgentChatRequest(
        String message,
        Integer maxCandidates
) {
}
