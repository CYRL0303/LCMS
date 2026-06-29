package com.legacypilot.repository.dto;

/**
 * Compact response returned by the Java backend after the Python code
 * knowledge service indexes a repository.
 */
public record RepositoryGraphAnalysisResponse(
        String repoId,
        String graphId,
        int nodeCount,
        int edgeCount,
        String generatedAt
) {
}
