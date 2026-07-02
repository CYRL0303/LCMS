package com.legacypilot.onboarding.source;

import com.legacypilot.onboarding.dto.OnboardProjectRequest;
import com.legacypilot.repository.entity.RepositorySourceType;
import com.legacypilot.repository.service.GitRepositoryService;
import com.legacypilot.repository.service.RepositoryService;
import org.springframework.stereotype.Component;

/**
 * Resolves an existing local Git working tree.
 */
@Component
public class LocalPathRepositorySourceResolver implements RepositorySourceResolver {
    private final RepositoryService repositoryService;

    public LocalPathRepositorySourceResolver(RepositoryService repositoryService) {
        this.repositoryService = repositoryService;
    }

    @Override
    public RepositorySourceType sourceType() {
        return RepositorySourceType.LOCAL_PATH;
    }

    @Override
    public ResolvedRepositorySource resolve(OnboardProjectRequest request) {
        GitRepositoryService.LocalGitRepository localRepository =
                repositoryService.inspectLocalRepository(request.localRepoPath(), null);
        return new ResolvedRepositorySource(sourceType(), localRepository);
    }
}
