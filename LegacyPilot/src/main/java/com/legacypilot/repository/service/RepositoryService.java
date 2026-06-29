package com.legacypilot.repository.service;

import com.legacypilot.project.entity.LegacyProject;
import com.legacypilot.project.service.ProjectService;
import com.legacypilot.repository.dto.ConnectRepositoryRequest;
import com.legacypilot.repository.dto.IndexRepositoryRequest;
import com.legacypilot.repository.dto.RepositoryFilesResponse;
import com.legacypilot.repository.entity.RepositoryIndex;
import com.legacypilot.repository.entity.RepositorySourceType;
import com.legacypilot.task.entity.AnalysisTask;
import com.legacypilot.task.entity.AnalysisTaskStatus;
import com.legacypilot.task.entity.AnalysisTaskType;
import com.legacypilot.task.service.TaskService;
import com.legacypilot.workspace.store.InMemoryWorkspaceStore;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Repository connection and file inspection service.
 */
@Service
public class RepositoryService {
    private final InMemoryWorkspaceStore store;
    private final ProjectService projectService;
    private final TaskService taskService;
    private final GitRepositoryService gitRepositoryService;
    private final RepositoryFileScannerService repositoryFileScannerService;

    public RepositoryService(
            InMemoryWorkspaceStore store,
            ProjectService projectService,
            TaskService taskService,
            GitRepositoryService gitRepositoryService,
            RepositoryFileScannerService repositoryFileScannerService
    ) {
        this.store = store;
        this.projectService = projectService;
        this.taskService = taskService;
        this.gitRepositoryService = gitRepositoryService;
        this.repositoryFileScannerService = repositoryFileScannerService;
    }

    public GitRepositoryService.LocalGitRepository inspectLocalRepository(String localRepoPath, String branch) {
        return gitRepositoryService.inspectLocalRepository(localRepoPath, branch);
    }

    public RepositoryIndex getRepository(String repoId) {
        RepositoryIndex repository = store.repositories().get(repoId);
        if (repository == null) {
            throw new ResponseStatusException(NOT_FOUND, "Repository not found: " + repoId);
        }
        return repository;
    }

    public RepositoryIndex indexRepository(IndexRepositoryRequest request) {
        requireText(request.projectId(), "projectId");
        LegacyProject project = projectService.getProject(request.projectId());

        String repositoryUrl = defaultValue(request.repositoryUrl(), project.repositoryUrl());
        requireText(repositoryUrl, "repositoryUrl");

        String repoId = newId("REPO");
        String taskId = newId("TASK");
        String createdAt = now();
        RepositoryIndex repository = new RepositoryIndex(
                repoId,
                project.projectId(),
                RepositorySourceType.GIT_URL,
                repositoryUrl,
                null,
                defaultValue(request.branch(), project.defaultBranch()),
                request.commitSha(),
                "GRAPH-" + repoId,
                taskId,
                createdAt
        );
        AnalysisTask task = new AnalysisTask(
                taskId,
                project.projectId(),
                repoId,
                null,
                AnalysisTaskType.REPO_INDEX,
                AnalysisTaskStatus.INDEXING_REPO,
                "Repository index task created. AI service integration is the next step.",
                createdAt,
                createdAt
        );

        store.repositories().put(repoId, repository);
        taskService.saveTask(task);
        return repository;
    }

    public RepositoryIndex connectRepository(ConnectRepositoryRequest request) {
        requireText(request.projectId(), "projectId");
        LegacyProject project = projectService.getProject(request.projectId());
        if (request.sourceType() == null) {
            throw new ResponseStatusException(BAD_REQUEST, "sourceType is required.");
        }
        if (request.sourceType() != RepositorySourceType.LOCAL_PATH) {
            throw new ResponseStatusException(BAD_REQUEST, "Only LOCAL_PATH is supported in the first local test.");
        }

        GitRepositoryService.LocalGitRepository localRepository =
                gitRepositoryService.inspectLocalRepository(request.localRepoPath(), request.branch());

        return createLocalRepositoryIndex(
                project,
                new GitRepositoryService.LocalGitRepository(
                        localRepository.localRepoPath(),
                        defaultValue(localRepository.repositoryUrl(), request.repositoryUrl()),
                        localRepository.branch(),
                        defaultValue(request.commitSha(), localRepository.commitSha())
                ),
                now()
        );
    }

    public RepositoryIndex createLocalRepositoryIndex(
            LegacyProject project,
            GitRepositoryService.LocalGitRepository localRepository,
            String createdAt
    ) {
        String repoId = newId("REPO");
        String taskId = newId("TASK");
        RepositoryIndex repository = new RepositoryIndex(
                repoId,
                project.projectId(),
                RepositorySourceType.LOCAL_PATH,
                localRepository.repositoryUrl(),
                localRepository.localRepoPath(),
                localRepository.branch(),
                localRepository.commitSha(),
                "GRAPH-" + repoId,
                taskId,
                createdAt
        );
        AnalysisTask task = new AnalysisTask(
                taskId,
                project.projectId(),
                repoId,
                null,
                AnalysisTaskType.REPO_INDEX,
                AnalysisTaskStatus.INDEXING_REPO,
                "Local repository connected and ready for GitNexus indexing.",
                createdAt,
                createdAt
        );

        store.repositories().put(repoId, repository);
        taskService.saveTask(task);
        return repository;
    }

    public RepositoryFilesResponse listRepositoryFiles(String repoId) {
        RepositoryIndex repository = getRepository(repoId);
        return repositoryFileScannerService.scanRepositoryFiles(repository);
    }

    private void requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, fieldName + " is required.");
        }
    }

    private String defaultValue(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value;
    }

    private String newId(String prefix) {
        return prefix + "-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    private String now() {
        return Instant.now().toString();
    }
}
