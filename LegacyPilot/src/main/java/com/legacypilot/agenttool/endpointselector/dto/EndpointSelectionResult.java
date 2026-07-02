package com.legacypilot.agenttool.endpointselector.dto;

import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import java.util.List;

/**
 * Result produced by the endpoint selector tool.
 */
public record EndpointSelectionResult(
        String repoId,
        String question,
        QueryUnderstandingResult query,
        List<EndpointCandidateResult> candidates
) {
}
