package com.legacypilot.agent.model;

/**
 * Model boundary for future Qwen integration.
 */
public interface AgentModelClient {
    AgentModelResponse complete(AgentModelRequest request);
}
