package com.legacypilot.agent.model;

/**
 * Model boundary for future Qwen API integration.
 */
public interface AgentModelClient {
    AgentModelResponse complete(AgentModelRequest request);
}
