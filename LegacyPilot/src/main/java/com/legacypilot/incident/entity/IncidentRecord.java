package com.legacypilot.incident.entity;

import com.legacypilot.task.entity.AnalysisTaskStatus;

/**
 * Stored incident metadata for the MVP.
 *
 * Future versions should add fields for EvidenceBundle, RCA report, reviewer
 * notes, and durable incident-memory IDs.
 */
public record IncidentRecord(
        /** Stable incident ID used by /api/incidents/{incidentId}. */
        String incidentId,
        /** Project where the incident occurred. */
        String projectId,
        /** Repository used for code evidence. */
        String repoId,
        /** Analysis task that created or updated this incident. */
        String taskId,
        /** Raw log/alert text submitted for analysis. */
        String rawLog,
        /** Optional stack trace submitted for analysis. */
        String stackTrace,
        /** Optional user-written incident description. */
        String errorDescription,
        /** Current incident review/storage state. */
        AnalysisTaskStatus status,
        /** Whether a human confirmed the result. */
        boolean confirmedByUser,
        /** Outcome supplied during confirmation. */
        String fixOutcome,
        /** Memory retention rule supplied during confirmation. */
        String retentionPolicy,
        /** ISO-8601 creation timestamp. */
        String createdAt,
        /** ISO-8601 last update timestamp. */
        String updatedAt
) {
}
