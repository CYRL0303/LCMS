package com.legacypilot.controller;

import com.legacypilot.dto.*;
import com.legacypilot.entity.AnalysisTask;
import com.legacypilot.entity.IncidentRecord;
import com.legacypilot.entity.LegacyProject;
import com.legacypilot.entity.RepositoryIndex;
import com.legacypilot.service.AnalysisService;
import java.util.Collection;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * HTTP API boundary for the first LegacyPilot backend slice.
 *
 * The controller intentionally contains no business logic. It receives JSON
 * requests from the frontend or API test tools, lets Spring deserialize them
 * into DTO records, and delegates all workflow decisions to AnalysisService.
 */
@RestController
@RequestMapping("/api")
public class AnalysisController {

    private final AnalysisService analysisService;

    public AnalysisController(AnalysisService analysisService) {
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
        return analysisService.connectLocalProject(request);
    }

    /**
     * Legacy placeholder endpoint for creating a repository index record from a
     * Git URL. It does not clone or call GitNexus yet.
     */
    @PostMapping("/repos/index")
    public RepositoryIndex indexRepository(@RequestBody IndexRepositoryRequest request) {
        return analysisService.indexRepository(request);
    }

    /**
     * Connects source code to a project. The first implemented mode is
     * LOCAL_PATH, which validates a local Git working tree and records its
     * branch/commit for later GitNexus indexing.
     */
    @PostMapping("/repos/connect")
    public RepositoryIndex connectRepository(@RequestBody ConnectRepositoryRequest request) {
        return analysisService.connectRepository(request);
    }

    /**
     * Creates an incident analysis task from a raw log/stack trace. Current MVP
     * behavior records the task and incident only; evidence/RCA generation is a
     * later AI-service integration point.
     */
    @PostMapping("/incidents/analyze")
    public AnalysisTask analyzeIncident(@RequestBody AnalyzeIncidentRequest request) {
        return analysisService.analyzeIncident(request);
    }

    /**
     * Looks up the current status of a repository-indexing or incident-analysis
     * task.
     */
    @GetMapping("/analysis/{taskId}")
    public AnalysisTask getTask(@PathVariable String taskId) {
        return analysisService.getTask(taskId);
    }

    /**
     * Returns the stored incident record for review/debugging.
     */
    @GetMapping("/incidents/{incidentId}")
    public IncidentRecord getIncident(@PathVariable String incidentId) {
        return analysisService.getIncident(incidentId);
    }

    /**
     * Marks an incident as user-confirmed. This mirrors the future rule that
     * only human-confirmed RCA results may be saved as long-term incident memory.
     */
    @PostMapping("/incidents/{incidentId}/confirm")
    public IncidentRecord confirmIncident(
            @PathVariable String incidentId,
            @RequestBody ConfirmIncidentRequest request
    ) {
        return analysisService.confirmIncident(incidentId, request);
    }

    @GetMapping("/repos/{repoId}/files")
    public RepositoryFilesResponse listRepositoryFiles(@PathVariable String repoId) {
        return analysisService.listRepositoryFiles(repoId);
    }
}
