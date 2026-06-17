package com.legacypilot.dto;

/**
 * Request body for confirming an incident after review.
 *
 * Confirmation is intentionally explicit because only confirmed incidents
 * should become reusable incident memory.
 */
public record ConfirmIncidentRequest(
        /** Must be true before the backend marks the incident as confirmed. */
        boolean userConfirmation,
        /** User-provided fix result, for example fixed, workaround, or invalid. */
        String fixOutcome,
        /** Retention choice for future incident memory storage. */
        String retentionPolicy
) {
}
