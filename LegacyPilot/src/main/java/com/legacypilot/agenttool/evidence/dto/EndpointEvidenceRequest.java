package com.legacypilot.agenttool.evidence.dto;

/**
 * Request DTO for reading source evidence linked to one endpoint.
 */
public record EndpointEvidenceRequest(
        String endpointId
) {
}
