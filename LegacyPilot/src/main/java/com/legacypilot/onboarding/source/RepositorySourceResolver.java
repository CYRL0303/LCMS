package com.legacypilot.onboarding.source;

import com.legacypilot.onboarding.dto.OnboardProjectRequest;
import com.legacypilot.repository.entity.RepositorySourceType;

/**
 * Resolves one supported onboarding source type into a local repository that
 * can be scanned and analyzed.
 */
public interface RepositorySourceResolver {
    RepositorySourceType sourceType();

    ResolvedRepositorySource resolve(OnboardProjectRequest request);
}
