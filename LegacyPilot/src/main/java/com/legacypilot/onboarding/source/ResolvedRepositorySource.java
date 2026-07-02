package com.legacypilot.onboarding.source;

import com.legacypilot.repository.entity.RepositorySourceType;
import com.legacypilot.repository.service.GitRepositoryService;

/**
 * Normalized repository source after onboarding has resolved the user input.
 */
public record ResolvedRepositorySource(
        RepositorySourceType sourceType,
        GitRepositoryService.LocalGitRepository localRepository
) {
}
