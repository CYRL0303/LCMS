package com.legacypilot.task.service;

import com.legacypilot.persistence.jdbc.TaskJdbcRepository;
import com.legacypilot.task.entity.AnalysisTask;
import com.legacypilot.task.entity.AnalysisTaskStatus;
import com.legacypilot.task.entity.AnalysisTaskType;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Task status service.
 */
@Service
public class TaskService {
    private final TaskJdbcRepository taskJdbcRepository;

    public TaskService(TaskJdbcRepository taskJdbcRepository) {
        this.taskJdbcRepository = taskJdbcRepository;
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
        return taskJdbcRepository.findById(taskId)
                .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Analysis task not found: " + taskId));
    }

    public void saveTask(AnalysisTask task) {
        taskJdbcRepository.save(task);
    }

    public String now() {
        return Instant.now().toString();
    }
}
