package com.legacypilot.controller;

import com.legacypilot.dto.ConnectLocalProjectRequest;
import com.legacypilot.dto.ConnectLocalProjectResponse;
import com.legacypilot.dto.CreateProjectRequest;
import com.legacypilot.entity.LegacyProject;
import com.legacypilot.service.AnalysisService;
import com.legacypilot.service.ProjectOnboardingService;
import java.util.Collection;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Project onboarding and project metadata endpoints.
 */
@RestController
@RequestMapping("/api")
public class ProjectController {
    private final AnalysisService analysisService;
    private final ProjectOnboardingService projectOnboardingService;

    public ProjectController(
            AnalysisService analysisService,
            ProjectOnboardingService projectOnboardingService
    ) {
        this.analysisService = analysisService;
        this.projectOnboardingService = projectOnboardingService;
    }

    /**
     * Creates a logical legacy-system project. A project can later have one or
     * more repository connections and incident analysis tasks.
     */
    @PostMapping("/projects")
    public LegacyProject createProject(@RequestBody CreateProjectRequest request) {
        return analysisService.createProject(request);
    }

    /**
     * Returns all in-memory projects for the current backend process.
     */
    @GetMapping("/projects")
    public Collection<LegacyProject> listProjects() {
        return analysisService.listProjects();
    }

    /**
     * One-shot local demo endpoint: create a project and connect a local Git
     * repository from one request so users do not need to copy projectId between
     * Postman calls.
     */
    @PostMapping("/onboarding/local-project")
    public ConnectLocalProjectResponse connectLocalProject(@RequestBody ConnectLocalProjectRequest request) {
        return projectOnboardingService.connectLocalProject(request);
    }
}
