package com.legacypilot.agent.model;

import org.springframework.stereotype.Component;

/**
 * Placeholder model client until Qwen is configured.
 */
@Component
public class NoOpAgentModelClient implements AgentModelClient {
    @Override
    public AgentModelResponse complete(AgentModelRequest request) {
        return new AgentModelResponse(
                "Qwen model client is not configured yet. Agent context has been prepared."
        );
    }
}
