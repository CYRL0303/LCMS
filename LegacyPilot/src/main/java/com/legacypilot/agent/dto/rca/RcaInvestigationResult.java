package com.legacypilot.agent.dto.rca;

import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import java.util.List;

/**
 * Lightweight investigation result assembled from existing agent tools.
 */
public record RcaInvestigationResult(
        String repoId,
        String question,
        QueryUnderstandingResult query,
        List<String> keywords,
        List<String> searchPlan,
        List<RcaEndpointCandidateResult> candidates,
        String agentContextText,
        String investigationSummary
) {
}
