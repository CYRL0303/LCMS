package com.legacypilot.onboarding.dto;

import com.legacypilot.repository.entity.RepositorySourceType;

/**
 * General project onboarding request. The source type decides whether the
 * repository comes from an existing local path or a remote Git URL.
 */
public record OnboardProjectRequest(
        String projectName,
        RepositorySourceType sourceType,
        String localRepoPath,
        String repositoryUrl,
        String branch,
        Boolean cloneToLocal
) {
}
