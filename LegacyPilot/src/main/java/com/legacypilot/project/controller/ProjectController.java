package com.legacypilot.project.controller;

import com.legacypilot.project.dto.CreateProjectRequest;
import com.legacypilot.project.entity.LegacyProject;
import com.legacypilot.project.service.ProjectService;
import java.util.Collection;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Project metadata endpoints.
 */
@RestController
@RequestMapping("/api")
public class ProjectController {
    private final ProjectService projectService;

    public ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    /**
     * Creates a logical legacy-system project. A project can later have one or
     * more repository connections and incident analysis tasks.
     */
    @PostMapping("/projects")
    public LegacyProject createProject(@RequestBody CreateProjectRequest request) {
        return projectService.createProject(request);
    }

    /**
     * Returns all in-memory projects for the current backend process.
     */
    @GetMapping("/projects")
    public Collection<LegacyProject> listProjects() {
        return projectService.listProjects();
    }
}
