package com.legacypilot.codeanalysis.service;

import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.persistence.jdbc.CodeAnalysisSnapshotJdbcRepository;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Temporary in-memory store for complete code analysis results.
 *
 * This keeps the current API usable before database or graph artifact
 * persistence is introduced.
 */
@Component
public class CodeAnalysisResultStore {
    private final CodeAnalysisSnapshotJdbcRepository snapshotJdbcRepository;

    public CodeAnalysisResultStore(CodeAnalysisSnapshotJdbcRepository snapshotJdbcRepository) {
        this.snapshotJdbcRepository = snapshotJdbcRepository;
    }

    public void save(String repoId, CodeAnalysisResult result) {
        snapshotJdbcRepository.insert(repoId, result);
    }

    public CodeAnalysisResult get(String repoId) {
        return snapshotJdbcRepository.findLatestByRepoId(repoId)
                .orElseThrow(() -> new ResponseStatusException(
                        NOT_FOUND,
                        "Code analysis result not found. Run analysis first."
                ));
    }
}
