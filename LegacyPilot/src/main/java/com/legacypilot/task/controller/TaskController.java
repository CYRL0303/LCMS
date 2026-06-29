package com.legacypilot.task.controller;

import com.legacypilot.task.entity.AnalysisTask;
import com.legacypilot.task.service.TaskService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Task status and backend readiness endpoints.
 */
@RestController
@RequestMapping("/api")
public class TaskController {
    private final TaskService taskService;

    public TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    /**
     * Lightweight readiness endpoint used during local development.
     */
    @GetMapping("/analysis/status")
    public AnalysisTask getStatus() {
        return taskService.getStatus();
    }

    /**
     * Looks up the current status of a repository-indexing or incident-analysis
     * task.
     */
    @GetMapping("/analysis/{taskId}")
    public AnalysisTask getTask(@PathVariable String taskId) {
        return taskService.getTask(taskId);
    }
}
