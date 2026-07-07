package com.legacypilot.onboarding.service;

import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.codeanalysis.service.RepositoryCodeAnalysisService;
import com.legacypilot.onboarding.dto.OnboardProjectRequest;
import com.legacypilot.onboarding.dto.OnboardProjectResponse;
import com.legacypilot.onboarding.source.RepositorySourceResolver;
import com.legacypilot.onboarding.source.ResolvedRepositorySource;
import com.legacypilot.project.entity.LegacyProject;
import com.legacypilot.project.service.ProjectService;
import com.legacypilot.repository.dto.RepositoryFilesResponse;
import com.legacypilot.repository.dto.RepositoryGraphAnalysisResponse;
import com.legacypilot.repository.entity.RepositoryIndex;
import com.legacypilot.repository.entity.RepositorySourceType;
import com.legacypilot.repository.service.RepositoryService;
import java.time.Instant;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

/**
 * Coordinates the full one-shot project onboarding workflow.
 *
 * This service owns the workflow sequence. Source-specific details are
 * delegated to repository source resolvers, while project/repository/code
 * analysis modules keep their own domain logic.
 */
@Service
public class ProjectOnboardingService {
    private final ProjectService projectService;
    private final RepositoryService repositoryService;
    private final RepositoryCodeAnalysisService repositoryCodeAnalysisService;
    private final AgentContextStore agentContextStore;
    private final Map<RepositorySourceType, RepositorySourceResolver> sourceResolvers;

    public ProjectOnboardingService(
            ProjectService projectService,
            RepositoryService repositoryService,
            RepositoryCodeAnalysisService repositoryCodeAnalysisService,
            AgentContextStore agentContextStore,
            List<RepositorySourceResolver> sourceResolvers
    ) {
        this.projectService = projectService;
        this.repositoryService = repositoryService;
        this.repositoryCodeAnalysisService = repositoryCodeAnalysisService;
        this.agentContextStore = agentContextStore;
        this.sourceResolvers = toResolverMap(sourceResolvers);
    }

    public OnboardProjectResponse onboardProject(OnboardProjectRequest request) {
        requireText(request.projectName(), "projectName");
        RepositorySourceType sourceType = request.sourceType() == null
                ? RepositorySourceType.LOCAL_PATH
                : request.sourceType();

        ResolvedRepositorySource source = resolverFor(sourceType).resolve(request);
        String createdAt = Instant.now().toString();
        LegacyProject project = projectService.findOrCreateProject(
                request.projectName(),
                source.localRepository().repositoryUrl(),
                source.localRepository().branch(),
                createdAt
        );
        RepositoryIndex repository = repositoryService.createLocalRepositoryIndex(
                project,
                source.localRepository(),
                createdAt
        );
        RepositoryFilesResponse files = repositoryService.listRepositoryFiles(repository.repoId());
        RepositoryGraphAnalysisResponse graph = repositoryCodeAnalysisService.analyzeRepository(repository.repoId());
        agentContextStore.setCurrentRepoId(repository.repoId());

        return new OnboardProjectResponse(
                project,
                repository,
                files,
                graph
        );
    }

    private RepositorySourceResolver resolverFor(RepositorySourceType sourceType) {
        RepositorySourceResolver resolver = sourceResolvers.get(sourceType);
        if (resolver == null) {
            throw new ResponseStatusException(BAD_REQUEST, "Unsupported onboarding sourceType: " + sourceType);
        }
        return resolver;
    }

    private Map<RepositorySourceType, RepositorySourceResolver> toResolverMap(
            List<RepositorySourceResolver> resolvers
    ) {
        Map<RepositorySourceType, RepositorySourceResolver> resolverMap =
                new EnumMap<>(RepositorySourceType.class);
        for (RepositorySourceResolver resolver : resolvers) {
            resolverMap.put(resolver.sourceType(), resolver);
        }
        return resolverMap;
    }

    private void requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, fieldName + " is required.");
        }
    }
}
