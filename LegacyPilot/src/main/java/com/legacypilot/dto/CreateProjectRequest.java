package com.legacypilot.dto;

/**
 * Request body for creating a logical legacy-system project.
 */
public record CreateProjectRequest(
        /** User-facing project name, also used later for default clone folders. */
        String name,
        /** Optional default repository URL for the project. */
        String repositoryUrl,
        /** Default branch to use when repository requests omit branch. */
        String defaultBranch
) {
}
