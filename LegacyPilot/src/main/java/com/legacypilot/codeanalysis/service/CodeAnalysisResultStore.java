package com.legacypilot.codeanalysis.service;

import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
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
    private final Map<String, CodeAnalysisResult> resultsByRepoId = new ConcurrentHashMap<>();

    public void save(String repoId, CodeAnalysisResult result) {
        resultsByRepoId.put(repoId, result);
    }

    public CodeAnalysisResult get(String repoId) {
        CodeAnalysisResult result = resultsByRepoId.get(repoId);
        if (result == null) {
            throw new ResponseStatusException(NOT_FOUND, "Code analysis result not found. Run analysis first.");
        }
        return result;
    }
}
