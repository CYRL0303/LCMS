package com.legacypilot.agenttool.contextbuilder.dto;

import com.legacypilot.agenttool.endpoint.dto.EndpointLookupResult;
import com.legacypilot.agenttool.evidence.dto.EndpointEvidenceResult;

/**
 * Endpoint candidate plus the source evidence selected for agent reasoning.
 */
public record AgentEndpointContextItem(
        EndpointLookupResult endpoint,
        EndpointEvidenceResult evidence,
        int score,
        String reason
) {
}
