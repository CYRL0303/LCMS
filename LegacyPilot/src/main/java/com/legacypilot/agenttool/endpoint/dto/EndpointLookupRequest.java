package com.legacypilot.agenttool.endpoint.dto;

/**
 * Request DTO for resolving one endpoint after the agent has selected it.
 */
public record EndpointLookupRequest(
        String path
) {
}
