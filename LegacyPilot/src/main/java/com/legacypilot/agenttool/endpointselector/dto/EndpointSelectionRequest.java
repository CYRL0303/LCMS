package com.legacypilot.agenttool.endpointselector.dto;

/**
 * Debug request for selecting likely endpoint candidates from a user question.
 */
public record EndpointSelectionRequest(
        String question,
        Integer maxCandidates
) {
}
