package com.legacypilot.codeanalysis.service;

import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.repository.dto.RepositoryGraphAnalysisResponse;
import com.legacypilot.repository.entity.RepositoryIndex;
import com.legacypilot.repository.service.RepositoryService;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

/**
 * Orchestrates repository-level code graph analysis.
 *
 * This service bridges Java repository metadata and the Python code knowledge
 * service. It does not perform HTTP itself; CodeKnowledgeClient owns that
 * external API detail.
 */
@Service
public class RepositoryCodeAnalysisService {
    private final RepositoryService repositoryService;
    private final JavaCodeAnalysisService javaCodeAnalysisService;
    // private final CodeKnowledgeClient codeKnowledgeClient;

    public RepositoryCodeAnalysisService(
            RepositoryService repositoryService,
            JavaCodeAnalysisService javaCodeAnalysisService
            // CodeKnowledgeClient codeKnowledgeClient
    ) {
        this.repositoryService = repositoryService;
        this.javaCodeAnalysisService = javaCodeAnalysisService;
        // this.codeKnowledgeClient = codeKnowledgeClient;
    }

    /**
     * Looks up a connected repository and indexes its code graph.
     */
    public RepositoryGraphAnalysisResponse analyzeRepository(String repoId) {
        RepositoryIndex repository = repositoryService.getRepository(repoId);
        if (repository.localRepoPath() == null || repository.localRepoPath().isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "Repository does not have a local path.");
        }

        CodeAnalysisResult analysisResult =
                javaCodeAnalysisService.analyze(repository.repoId(), repository.localRepoPath());

        return new RepositoryGraphAnalysisResponse(
                repository.repoId(),
                "GRAPH-" + repository.repoId(),
                analysisResult.summary().nodeCount(),
                analysisResult.summary().edgeCount(),
                Instant.now().toString()
        );

        /*
        CodeKnowledgeGraphSnapshotResponse graphSnapshot =
                codeKnowledgeClient.indexRepository(repository.repoId(), repository.localRepoPath());

        return new RepositoryGraphAnalysisResponse(
                repository.repoId(),
                graphSnapshot.graphId(),
                graphSnapshot.nodeCount(),
                graphSnapshot.edgeCount(),
                graphSnapshot.generatedAt()
        );
        */
    }
}
