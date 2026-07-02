package com.legacypilot.agenttool.endpointselector.dto;

import com.legacypilot.agenttool.endpoint.dto.EndpointLookupResult;

/**
 * One endpoint candidate selected from the analyzed project.
 */
public record EndpointCandidateResult(
        EndpointLookupResult endpoint,
        int score,
        String reason
) {
}
