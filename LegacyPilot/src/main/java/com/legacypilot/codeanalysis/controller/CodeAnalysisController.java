package com.legacypilot.codeanalysis.controller;

import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.service.RepositoryCodeAnalysisService;
import com.legacypilot.repository.dto.RepositoryGraphAnalysisResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Code analysis endpoints for graph summaries and full analysis results.
 */
@RestController
@RequestMapping("/api/code-analysis")
public class CodeAnalysisController {
    private final RepositoryCodeAnalysisService repositoryCodeAnalysisService;

    public CodeAnalysisController(RepositoryCodeAnalysisService repositoryCodeAnalysisService) {
        this.repositoryCodeAnalysisService = repositoryCodeAnalysisService;
    }

    /**
     * Runs code analysis for a connected repository and stores the full result
     * in memory for later graph/detail queries.
     */
    @PostMapping("/repos/{repoId}/analyze")
    public RepositoryGraphAnalysisResponse analyzeRepository(@PathVariable String repoId) {
        return repositoryCodeAnalysisService.analyzeRepository(repoId);
    }

    /**
     * Returns the full code analysis result from the latest analysis run.
     */
    @GetMapping("/repos/{repoId}/graph")
    public CodeAnalysisResult getRepositoryGraph(@PathVariable String repoId) {
        return repositoryCodeAnalysisService.getAnalysisResult(repoId);
    }
}
