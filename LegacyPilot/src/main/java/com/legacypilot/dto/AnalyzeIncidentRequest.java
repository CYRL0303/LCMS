package com.legacypilot.dto;

/**
 * Request body for creating an incident-analysis task.
 *
 * The frontend will build this JSON from a form where the user pastes logs,
 * stack traces, and a short incident description. The Java backend stores the
 * request first; later LCMS ai-service will turn it into EvidenceBundle/RCA.
 */
public record AnalyzeIncidentRequest(
        /** Project that owns the connected repository. */
        String projectId,
        /** Repository connection/index to analyze against. */
        String repoId,
        /** Raw alert or log text supplied by the user or monitoring system. */
        String rawLog,
        /** Optional Java stack trace. */
        String stackTrace,
        /** Optional human-written explanation of what happened. */
        String errorDescription,
        /** Origin of the incident input, such as manual, alertmanager, or api. */
        String source
) {
}
