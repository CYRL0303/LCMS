package com.legacypilot.dto;

import com.legacypilot.entity.RepositorySourceType;

/**
 * Request body for connecting source code to a project.
 *
 * First local test supports LOCAL_PATH only. The same DTO already reserves
 * fields for later GIT_URL clone and custom target-directory behavior.
 */
public record ConnectRepositoryRequest(
        /** Existing LegacyPilot project ID. */
        String projectId,
        /** LOCAL_PATH for now; GIT_URL will be added later. */
        RepositorySourceType sourceType,
        /** Existing local Git working tree path when sourceType is LOCAL_PATH. */
        String localRepoPath,
        /** Remote Git URL when sourceType is GIT_URL, or optional metadata. */
        String repositoryUrl,
        /** Expected branch. For LOCAL_PATH it must match the current checkout. */
        String branch,
        /** Optional commit SHA for future checkout/analysis pinning. */
        String commitSha,
        /** Optional base directory for future GIT_URL clone mode. */
        String targetDirectory
) {
}
