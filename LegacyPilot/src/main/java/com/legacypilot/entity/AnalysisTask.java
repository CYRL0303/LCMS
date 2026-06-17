package com.legacypilot.entity;

/**
 * Backend task record returned to the frontend for polling/status display.
 *
 * A task can represent repository indexing or incident analysis. In this MVP it
 * is stored in memory; later it should become a database table and drive async
 * workers.
 */
public record AnalysisTask(
        /** Stable task ID used by GET /api/analysis/{taskId}. */
        String taskId,
        /** Project that owns this task. */
        String projectId,
        /** Repository involved in the task, when applicable. */
        String repoId,
        /** Incident involved in the task, when applicable. */
        String incidentId,
        /** High-level category of work. */
        AnalysisTaskType type,
        /** Current workflow state. */
        AnalysisTaskStatus status,
        /** Human-readable status/debug message. */
        String message,
        /** ISO-8601 creation timestamp. */
        String createdAt,
        /** ISO-8601 last update timestamp. */
        String updatedAt
) {
}
