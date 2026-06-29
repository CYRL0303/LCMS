package com.legacypilot.common.error;

/**
 * Stable error envelope returned by backend controllers.
 */
public record ApiErrorResponse(
        int status,
        String error,
        String message,
        String path
) {
}
