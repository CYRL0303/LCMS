package com.legacypilot.controller;

import com.legacypilot.entity.AnalysisTask;
import com.legacypilot.service.AnalysisService;
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
    private final AnalysisService analysisService;

    public TaskController(AnalysisService analysisService) {
        this.analysisService = analysisService;
    }

    /**
     * Lightweight readiness endpoint used during local development.
     */
    @GetMapping("/analysis/status")
    public AnalysisTask getStatus() {
        return analysisService.getStatus();
    }

    /**
     * Looks up the current status of a repository-indexing or incident-analysis
     * task.
     */
    @GetMapping("/analysis/{taskId}")
    public AnalysisTask getTask(@PathVariable String taskId) {
        return analysisService.getTask(taskId);
    }
}
