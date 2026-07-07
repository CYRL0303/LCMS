package com.legacypilot.codeanalysis.controller;

import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.dto.EndpointTraceResult;
import com.legacypilot.codeanalysis.service.EndpointTraceService;
import com.legacypilot.codeanalysis.service.RepositoryCodeAnalysisService;
import com.legacypilot.repository.dto.RepositoryGraphAnalysisResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Code analysis endpoints for graph summaries and full analysis results.
 */
@RestController
@RequestMapping("/api/code-analysis")
public class CodeAnalysisController {
    private final RepositoryCodeAnalysisService repositoryCodeAnalysisService;
    private final EndpointTraceService endpointTraceService;

    public CodeAnalysisController(
            RepositoryCodeAnalysisService repositoryCodeAnalysisService,
            EndpointTraceService endpointTraceService
    ) {
        this.repositoryCodeAnalysisService = repositoryCodeAnalysisService;
        this.endpointTraceService = endpointTraceService;
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

    /**
     * Traces one endpoint to its handler method and downstream method calls.
     *
     * endpointId is accepted as a query parameter because endpoint ids contain
     * HTTP paths with slashes.
     */
    @GetMapping("/repos/{repoId}/endpoint-trace")
    public EndpointTraceResult traceEndpoint(
            @PathVariable String repoId,
            @RequestParam(required = false) String endpointId,
            @RequestParam(required = false) String httpMethod,
            @RequestParam(required = false) String path,
            @RequestParam(required = false) Integer maxDepth
    ) {
        return endpointTraceService.traceEndpoint(repoId, endpointId, httpMethod, path, maxDepth);
    }
}
