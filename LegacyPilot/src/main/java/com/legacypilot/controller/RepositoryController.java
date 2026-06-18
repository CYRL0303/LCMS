package com.legacypilot.controller;

import com.legacypilot.dto.ConnectRepositoryRequest;
import com.legacypilot.dto.IndexRepositoryRequest;
import com.legacypilot.dto.RepositoryFilesResponse;
import com.legacypilot.dto.RepositoryGraphAnalysisResponse;
import com.legacypilot.entity.RepositoryIndex;
import com.legacypilot.service.AnalysisService;
import com.legacypilot.service.RepositoryCodeAnalysisService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Repository connection and repository file inspection endpoints.
 */
@RestController
@RequestMapping("/api")
public class RepositoryController {
    private final AnalysisService analysisService;
    private final RepositoryCodeAnalysisService repositoryCodeAnalysisService;

    public RepositoryController(
            AnalysisService analysisService,
            RepositoryCodeAnalysisService repositoryCodeAnalysisService
    ) {
        this.analysisService = analysisService;
        this.repositoryCodeAnalysisService = repositoryCodeAnalysisService;
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
     * Lists source/config/build/markdown files discovered in a connected
     * repository.
     */
    @GetMapping("/repos/{repoId}/files")
    public RepositoryFilesResponse listRepositoryFiles(@PathVariable String repoId) {
        return analysisService.listRepositoryFiles(repoId);
    }

    /**
     * Sends a connected repository to the Python code knowledge service and
     * returns a compact graph summary.
     */
    @PostMapping("/repos/{repoId}/analyze")
    public RepositoryGraphAnalysisResponse analyzeRepository(@PathVariable String repoId) {
        return repositoryCodeAnalysisService.analyzeRepository(repoId);
    }
}
