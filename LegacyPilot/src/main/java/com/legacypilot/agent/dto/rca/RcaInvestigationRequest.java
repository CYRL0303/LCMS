package com.legacypilot.agent.dto.rca;

/**
 * Request DTO for a lightweight RCA investigation over the current project.
 */
public record RcaInvestigationRequest(
        String question,
        Integer maxCandidates
) {
}
