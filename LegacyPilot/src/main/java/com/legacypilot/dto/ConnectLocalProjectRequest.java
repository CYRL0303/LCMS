package com.legacypilot.dto;

/**
 * One-shot request for the first local demo flow.
 *
 * The user supplies only a display project name and an existing local Git
 * working tree. The backend creates the project, connects the repository, and
 * returns every generated ID in one response.
 */
public record ConnectLocalProjectRequest(
        /** User-facing project name. */
        String projectName,
        /** Existing local Git working tree path. */
        String localRepoPath
) {
}
