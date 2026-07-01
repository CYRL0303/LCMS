package com.legacypilot.onboarding.service;

import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.codeanalysis.service.RepositoryCodeAnalysisService;
import com.legacypilot.onboarding.dto.ConnectLocalProjectRequest;
import com.legacypilot.onboarding.dto.ConnectLocalProjectResponse;
import com.legacypilot.project.entity.LegacyProject;
import com.legacypilot.project.service.ProjectService;
import com.legacypilot.repository.dto.RepositoryGraphAnalysisResponse;
import com.legacypilot.repository.dto.RepositoryFilesResponse;
import com.legacypilot.repository.entity.RepositoryIndex;
import com.legacypilot.repository.service.GitRepositoryService;
import com.legacypilot.repository.service.RepositoryService;
import java.time.Instant;
import org.springframework.stereotype.Service;

/**
 * Coordinates the full one-shot local project onboarding workflow.
 *
 * Domain services own project/repository creation and file scanning. This
 * service adds workflow sequencing so the main frontend flow can stay one API
 * call.
 */
@Service
public class ProjectOnboardingService {
    private final ProjectService projectService;
    private final RepositoryService repositoryService;
    private final RepositoryCodeAnalysisService repositoryCodeAnalysisService;
    private final AgentContextStore agentContextStore;

    public ProjectOnboardingService(
            ProjectService projectService,
            RepositoryService repositoryService,
            RepositoryCodeAnalysisService repositoryCodeAnalysisService,
            AgentContextStore agentContextStore
    ) {
        this.projectService = projectService;
        this.repositoryService = repositoryService;
        this.repositoryCodeAnalysisService = repositoryCodeAnalysisService;
        this.agentContextStore = agentContextStore;
    }

    /**
     * Creates the project/repository, scans files, then indexes the repository
     * through the Python code knowledge service.
     */
    public ConnectLocalProjectResponse connectLocalProject(ConnectLocalProjectRequest request) {
        GitRepositoryService.LocalGitRepository localRepository =
                repositoryService.inspectLocalRepository(request.localRepoPath(), null);

        String createdAt = Instant.now().toString();
        LegacyProject project = projectService.createProject(
                request.projectName(),
                localRepository.repositoryUrl(),
                localRepository.branch(),
                createdAt
        );
        RepositoryIndex repository = repositoryService.createLocalRepositoryIndex(
                project,
                localRepository,
                createdAt
        );
        RepositoryFilesResponse files = repositoryService.listRepositoryFiles(repository.repoId());
        RepositoryGraphAnalysisResponse graph = repositoryCodeAnalysisService.analyzeRepository(repository.repoId());
        agentContextStore.setCurrentRepoId(repository.repoId());

        return new ConnectLocalProjectResponse(
                project,
                repository,
                files,
                graph
        );
    }
}
