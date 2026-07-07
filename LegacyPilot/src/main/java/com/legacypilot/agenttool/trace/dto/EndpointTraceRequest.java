package com.legacypilot.agenttool.trace.dto;

/**
 * Request DTO for tracing one endpoint from the current repository graph.
 */
public record EndpointTraceRequest(
        String endpointId,
        String httpMethod,
        String path,
        Integer maxDepth
) {
}
