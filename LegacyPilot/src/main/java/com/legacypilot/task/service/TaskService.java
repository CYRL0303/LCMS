package com.legacypilot.task.service;

import com.legacypilot.task.entity.AnalysisTask;
import com.legacypilot.task.entity.AnalysisTaskStatus;
import com.legacypilot.task.entity.AnalysisTaskType;
import com.legacypilot.workspace.store.InMemoryWorkspaceStore;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Task status service.
 */
@Service
public class TaskService {
    private final InMemoryWorkspaceStore store;

    public TaskService(InMemoryWorkspaceStore store) {
        this.store = store;
    }

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

    public AnalysisTask getTask(String taskId) {
        AnalysisTask task = store.tasks().get(taskId);
        if (task == null) {
            throw new ResponseStatusException(NOT_FOUND, "Analysis task not found: " + taskId);
        }
        return task;
    }

    public void saveTask(AnalysisTask task) {
        store.tasks().put(task.taskId(), task);
    }

    public String now() {
        return Instant.now().toString();
    }
}
