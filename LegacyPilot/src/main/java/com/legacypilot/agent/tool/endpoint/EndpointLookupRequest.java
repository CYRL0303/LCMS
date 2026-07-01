package com.legacypilot.agent.tool.endpoint;

/**
 * Debug/internal input for resolving one endpoint after the agent has selected it.
 */
public record EndpointLookupRequest(
        String path
) {
}
