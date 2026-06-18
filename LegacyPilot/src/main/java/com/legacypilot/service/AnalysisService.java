package com.legacypilot.service;

import com.legacypilot.dto.*;
import com.legacypilot.entity.AnalysisTask;
import com.legacypilot.entity.AnalysisTaskStatus;
import com.legacypilot.entity.AnalysisTaskType;
import com.legacypilot.entity.IncidentRecord;
import com.legacypilot.entity.LegacyProject;
import com.legacypilot.entity.RepositoryIndex;
import com.legacypilot.entity.RepositorySourceType;
import java.time.Instant;
import java.util.Collection;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * First-pass application service for the Java backend.
 *
 * This class currently uses in-memory maps so the API shape can be tested
 * before adding persistence. The maps will later be replaced by database
 * repositories, and the repository/incident workflows will call LCMS ai-service
 * for GitNexus, RAG, and Qwen RCA generation.
 */
@Service
public class AnalysisService {
    private final GitRepositoryService gitRepositoryService;
    private final RepositoryFileScannerService repositoryFileScannerService;

    // Process-local stores. These are intentionally temporary: restarting the
    // backend clears them.
    private final Map<String, LegacyProject> projects = new ConcurrentHashMap<>();
    private final Map<String, RepositoryIndex> repositories = new ConcurrentHashMap<>();
    private final Map<String, AnalysisTask> tasks = new ConcurrentHashMap<>();
    private final Map<String, IncidentRecord> incidents = new ConcurrentHashMap<>();

    public AnalysisService(
            GitRepositoryService gitRepositoryService,
            RepositoryFileScannerService repositoryFileScannerService
    ) {
        this.gitRepositoryService = gitRepositoryService;
        this.repositoryFileScannerService = repositoryFileScannerService;
    }

    /**
     * Returns a synthetic status task so callers can confirm the backend is up.
     */
    public AnalysisTask getStatus() {
        String now = now();
        return new AnalysisTask(
                "TASK-STATUS",
                null,
                null,
                null,
                AnalysisTaskType.INCIDENT_ANALYSIS,
                AnalysisTaskStatus.PENDING,
                "LegacyPilot backend is ready.",
                now,
                now
        );
    }

    /**
     * Creates a logical project that groups one or more legacy repositories.
     */
    public LegacyProject createProject(CreateProjectRequest request) {
        requireText(request.name(), "name");

        String projectId = newId("PROJ");
        LegacyProject project = new LegacyProject(
                projectId,
                request.name(),
                request.repositoryUrl(),
                defaultValue(request.defaultBranch(), "main"),
                now()
        );
        projects.put(projectId, project);
        return project;
    }

    /**
     * Lists the projects known to the current backend process.
     */
    public Collection<LegacyProject> listProjects() {
        return projects.values();
    }

    /**
     * Looks up a connected repository by ID.
     *
     * This is a temporary read boundary over the in-memory store. When SQL is
     * added, callers should move to a repository/mapper abstraction without
     * changing their business flow.
     */
    public RepositoryIndex getRepository(String repoId) {
        RepositoryIndex repository = repositories.get(repoId);
        if (repository == null) {
            throw new ResponseStatusException(NOT_FOUND, "Repository not found: " + repoId);
        }
        return repository;
    }

    /**
     * Creates a project and connects a local Git repository in one call.
     *
     * This endpoint is intended for the first local demo and Postman testing.
     * It avoids a fragile manual flow where the user has to copy projectId from
     * one request into the next request.
     */
    public ConnectLocalProjectResponse connectLocalProject(ConnectLocalProjectRequest request) {
        requireText(request.projectName(), "projectName");

        GitRepositoryService.LocalGitRepository localRepository =
                gitRepositoryService.inspectLocalRepository(request.localRepoPath(), null);

        String createdAt = now();
        String projectId = newId("PROJ");
        LegacyProject project = new LegacyProject(
                projectId,
                request.projectName(),
                localRepository.repositoryUrl(),
                localRepository.branch(),
                createdAt
        );
        projects.put(projectId, project);

        RepositoryIndex repository = createLocalRepositoryIndex(project, localRepository, createdAt);
        RepositoryFilesResponse files = listRepositoryFiles(repository.repoId());
        return new ConnectLocalProjectResponse(project, repository, files, null);
    }

    /**
     * Placeholder for the future Git-URL indexing path.
     *
     * This method only creates an index record and task. It does not clone the
     * repository yet. The newer connectRepository method should be used for the
     * first real local-path test.
     */
    public RepositoryIndex indexRepository(IndexRepositoryRequest request) {
        requireText(request.projectId(), "projectId");
        LegacyProject project = projects.get(request.projectId());
        if (project == null) {
            throw new ResponseStatusException(NOT_FOUND, "Project not found: " + request.projectId());
        }

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

        repositories.put(repoId, repository);
        tasks.put(taskId, task);
        return repository;
    }

    /**
     * Connects a codebase to a project.
     *
     * Current behavior supports only LOCAL_PATH: the backend validates that the
     * path is an existing Git working tree, reads its branch/commit, and stores a
     * RepositoryIndex record. Future behavior can add GIT_URL clone and conflict
     * handling without changing the controller endpoint.
     */
    public RepositoryIndex connectRepository(ConnectRepositoryRequest request) {
        requireText(request.projectId(), "projectId");
        LegacyProject project = projects.get(request.projectId());
        if (project == null) {
            throw new ResponseStatusException(NOT_FOUND, "Project not found: " + request.projectId());
        }
        if (request.sourceType() == null) {
            throw new ResponseStatusException(BAD_REQUEST, "sourceType is required.");
        }
        if (request.sourceType() != RepositorySourceType.LOCAL_PATH) {
            throw new ResponseStatusException(BAD_REQUEST, "Only LOCAL_PATH is supported in the first local test.");
        }

        // Delegate Git-specific validation/inspection so this service stays
        // focused on product workflow state.
        GitRepositoryService.LocalGitRepository localRepository =
                gitRepositoryService.inspectLocalRepository(request.localRepoPath(), request.branch());

        String createdAt = now();
        return createLocalRepositoryIndex(
                project,
                new GitRepositoryService.LocalGitRepository(
                        localRepository.localRepoPath(),
                        defaultValue(localRepository.repositoryUrl(), request.repositoryUrl()),
                        localRepository.branch(),
                        defaultValue(request.commitSha(), localRepository.commitSha())
                ),
                createdAt
        );
    }

    /**
     * Creates an incident-analysis task for a connected repository.
     *
     * This currently records the incident and moves it directly to
     * WAITING_REVIEW. Later, this is where the service should enqueue/call the
     * AI flow: build evidence, generate RCA, review RCA, then wait for user
     * confirmation.
     */
    public AnalysisTask analyzeIncident(AnalyzeIncidentRequest request) {
        requireText(request.projectId(), "projectId");
        requireText(request.repoId(), "repoId");
        requireText(request.rawLog(), "rawLog");

        if (!projects.containsKey(request.projectId())) {
            throw new ResponseStatusException(NOT_FOUND, "Project not found: " + request.projectId());
        }
        RepositoryIndex repository = repositories.get(request.repoId());
        if (repository == null) {
            throw new ResponseStatusException(NOT_FOUND, "Repository index not found: " + request.repoId());
        }
        if (!repository.projectId().equals(request.projectId())) {
            throw new ResponseStatusException(BAD_REQUEST, "Repository does not belong to project.");
        }

        String incidentId = newId("INC");
        String taskId = newId("TASK");
        String createdAt = now();

        IncidentRecord incident = new IncidentRecord(
                incidentId,
                request.projectId(),
                request.repoId(),
                taskId,
                request.rawLog(),
                request.stackTrace(),
                request.errorDescription(),
                AnalysisTaskStatus.WAITING_REVIEW,
                false,
                null,
                null,
                createdAt,
                createdAt
        );
        AnalysisTask task = new AnalysisTask(
                taskId,
                request.projectId(),
                request.repoId(),
                incidentId,
                AnalysisTaskType.INCIDENT_ANALYSIS,
                AnalysisTaskStatus.WAITING_REVIEW,
                "Incident analysis task created. Evidence/RCA generation is still mocked by task state.",
                createdAt,
                createdAt
        );

        incidents.put(incidentId, incident);
        tasks.put(taskId, task);
        return task;
    }

    /**
     * Fetches a task by ID or returns a 404 response.
     */
    public AnalysisTask getTask(String taskId) {
        AnalysisTask task = tasks.get(taskId);
        if (task == null) {
            throw new ResponseStatusException(NOT_FOUND, "Analysis task not found: " + taskId);
        }
        return task;
    }

    /**
     * Fetches an incident by ID or returns a 404 response.
     */
    public IncidentRecord getIncident(String incidentId) {
        IncidentRecord incident = incidents.get(incidentId);
        if (incident == null) {
            throw new ResponseStatusException(NOT_FOUND, "Incident not found: " + incidentId);
        }
        return incident;
    }

    /**
     * Applies human confirmation to an incident.
     *
     * This method encodes a key product rule from the architecture document:
     * only user-confirmed RCA results should become durable incident memory.
     */
    public IncidentRecord confirmIncident(String incidentId, ConfirmIncidentRequest request) {
        if (!request.userConfirmation()) {
            throw new ResponseStatusException(BAD_REQUEST, "Incident memory requires user confirmation.");
        }
        IncidentRecord current = getIncident(incidentId);
        String updatedAt = now();
        IncidentRecord confirmed = new IncidentRecord(
                current.incidentId(),
                current.projectId(),
                current.repoId(),
                current.taskId(),
                current.rawLog(),
                current.stackTrace(),
                current.errorDescription(),
                AnalysisTaskStatus.CONFIRMED,
                true,
                defaultValue(request.fixOutcome(), "pending"),
                defaultValue(request.retentionPolicy(), "default"),
                current.createdAt(),
                updatedAt
        );
        incidents.put(incidentId, confirmed);

        AnalysisTask currentTask = getTask(current.taskId());
        tasks.put(current.taskId(), new AnalysisTask(
                currentTask.taskId(),
                currentTask.projectId(),
                currentTask.repoId(),
                currentTask.incidentId(),
                currentTask.type(),
                AnalysisTaskStatus.CONFIRMED,
                "Incident confirmed by user and ready to be stored as memory.",
                currentTask.createdAt(),
                updatedAt
        ));
        return confirmed;
    }

    /**
     * Validates required string fields before creating business records.
     */
    private void requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, fieldName + " is required.");
        }
    }

    /**
     * Returns fallback when a request field is blank.
     */
    private String defaultValue(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value;
    }

    /**
     * Persists a connected local repository into the in-memory repository/task
     * stores. Both the one-shot onboarding endpoint and the lower-level
     * /api/repos/connect endpoint use this helper.
     */
    private RepositoryIndex createLocalRepositoryIndex(
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

        repositories.put(repoId, repository);
        tasks.put(taskId, task);
        return repository;
    }

    /**
     * Generates compact, non-sequential IDs for local and future multi-user use.
     *
     * The prefix keeps records easy to identify in logs and API responses while
     * UUID randomness avoids collisions across backend restarts.
     */
    private String newId(String prefix) {
        return prefix + "-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    /**
     * Stores timestamps as ISO-8601 strings for the MVP. A later database model
     * can switch these fields to Instant directly.
     */
    private String now() {
        return Instant.now().toString();
    }

    /**
     * Scans the connected repository directory and returns a lightweight file
     * summary. This proves repoId -> localRepoPath -> readable source files
     * works before GitNexus integration is added.
     */
    public RepositoryFilesResponse listRepositoryFiles(String repoId) {
        RepositoryIndex repository = getRepository(repoId);
        return repositoryFileScannerService.scanRepositoryFiles(repository);
    }
}
