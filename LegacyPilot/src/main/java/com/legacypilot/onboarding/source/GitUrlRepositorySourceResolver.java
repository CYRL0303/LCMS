package com.legacypilot.onboarding.source;

import com.legacypilot.onboarding.dto.OnboardProjectRequest;
import com.legacypilot.repository.entity.RepositorySourceType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.NOT_IMPLEMENTED;

/**
 * Placeholder resolver for public Git URL onboarding.
 *
 * The workflow is intentionally separated now so clone support can be added
 * without changing the controller or orchestration service.
 */
@Component
public class GitUrlRepositorySourceResolver implements RepositorySourceResolver {
    @Override
    public RepositorySourceType sourceType() {
        return RepositorySourceType.GIT_URL;
    }

    @Override
    public ResolvedRepositorySource resolve(OnboardProjectRequest request) {
        if (request.repositoryUrl() == null || request.repositoryUrl().isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "repositoryUrl is required for GIT_URL onboarding.");
        }
        if (request.cloneToLocal() == null || !request.cloneToLocal()) {
            throw new ResponseStatusException(BAD_REQUEST, "cloneToLocal must be true for GIT_URL onboarding.");
        }
        throw new ResponseStatusException(
                NOT_IMPLEMENTED,
                "GIT_URL onboarding is reserved. Public Git clone support will be implemented next."
        );
    }
}
