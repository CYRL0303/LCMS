package com.legacypilot.agent.dto.rca;

import com.legacypilot.agenttool.endpoint.dto.EndpointLookupResult;
import com.legacypilot.agenttool.evidence.dto.EndpointEvidenceResult;
import com.legacypilot.agenttool.trace.dto.EndpointTraceToolResult;

/**
 * One endpoint candidate selected for an investigation question.
 */
public record RcaEndpointCandidateResult(
        EndpointLookupResult endpoint,
        EndpointEvidenceResult evidence,
        EndpointTraceToolResult trace,
        int score,
        String reason
) {
}
