package com.legacypilot.dto;

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
