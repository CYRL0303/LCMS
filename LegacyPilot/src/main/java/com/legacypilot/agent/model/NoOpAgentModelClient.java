package com.legacypilot.agent.model;

import org.springframework.stereotype.Component;

/**
 * Placeholder model client until Qwen API integration is wired.
 */
@Component
public class NoOpAgentModelClient implements AgentModelClient {
    @Override
    public AgentModelResponse complete(AgentModelRequest request) {
        return new AgentModelResponse("Qwen model client is not configured yet. Tool context has been prepared.");
    }
}
