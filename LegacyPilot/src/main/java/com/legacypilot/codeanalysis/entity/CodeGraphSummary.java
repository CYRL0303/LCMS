package com.legacypilot.codeanalysis.entity;

/**
 * Compact graph statistics for page summaries and onboarding responses.
 */
public record CodeGraphSummary(
        String repoId,
        String projectType,
        int nodeCount,
        int edgeCount,
        int classCount,
        int methodCount,
        int endpointCount
) {
}
