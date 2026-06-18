package com.legacypilot.service;

import com.legacypilot.dto.CodeKnowledgeGraphSnapshotResponse;
import com.legacypilot.dto.RepositoryGraphAnalysisResponse;
import com.legacypilot.entity.RepositoryIndex;
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
    private final AnalysisService analysisService;
    private final CodeKnowledgeClient codeKnowledgeClient;

    public RepositoryCodeAnalysisService(
            AnalysisService analysisService,
            CodeKnowledgeClient codeKnowledgeClient
    ) {
        this.analysisService = analysisService;
        this.codeKnowledgeClient = codeKnowledgeClient;
    }

    /**
     * Looks up a connected repository and asks Python to index its code graph.
     */
    public RepositoryGraphAnalysisResponse analyzeRepository(String repoId) {
        RepositoryIndex repository = analysisService.getRepository(repoId);
        if (repository.localRepoPath() == null || repository.localRepoPath().isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "Repository does not have a local path.");
        }

        CodeKnowledgeGraphSnapshotResponse graphSnapshot =
                codeKnowledgeClient.indexRepository(repository.repoId(), repository.localRepoPath());

        return new RepositoryGraphAnalysisResponse(
                repository.repoId(),
                graphSnapshot.graphId(),
                graphSnapshot.nodeCount(),
                graphSnapshot.edgeCount(),
                graphSnapshot.generatedAt()
        );
    }
}
