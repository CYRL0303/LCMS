package com.legacypilot.incident.service;

import com.legacypilot.incident.dto.AnalyzeIncidentRequest;
import com.legacypilot.incident.dto.ConfirmIncidentRequest;
import com.legacypilot.incident.entity.IncidentRecord;
import com.legacypilot.project.service.ProjectService;
import com.legacypilot.repository.entity.RepositoryIndex;
import com.legacypilot.repository.service.RepositoryService;
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
 * Incident analysis and confirmation service.
 */
@Service
public class IncidentService {
    private final InMemoryWorkspaceStore store;
    private final ProjectService projectService;
    private final RepositoryService repositoryService;
    private final TaskService taskService;

    public IncidentService(
            InMemoryWorkspaceStore store,
            ProjectService projectService,
            RepositoryService repositoryService,
            TaskService taskService
    ) {
        this.store = store;
        this.projectService = projectService;
        this.repositoryService = repositoryService;
        this.taskService = taskService;
    }

    public AnalysisTask analyzeIncident(AnalyzeIncidentRequest request) {
        requireText(request.projectId(), "projectId");
        requireText(request.repoId(), "repoId");
        requireText(request.rawLog(), "rawLog");

        projectService.getProject(request.projectId());
        RepositoryIndex repository = repositoryService.getRepository(request.repoId());
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

        store.incidents().put(incidentId, incident);
        taskService.saveTask(task);
        return task;
    }

    public IncidentRecord getIncident(String incidentId) {
        IncidentRecord incident = store.incidents().get(incidentId);
        if (incident == null) {
            throw new ResponseStatusException(NOT_FOUND, "Incident not found: " + incidentId);
        }
        return incident;
    }

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
        store.incidents().put(incidentId, confirmed);

        AnalysisTask currentTask = taskService.getTask(current.taskId());
        taskService.saveTask(new AnalysisTask(
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
