package com.legacypilot.codeanalysis.entity;

/**
 * Traceable source evidence supporting a parsed code fact.
 */
public record EvidenceRef(
        String evidenceId,
        String filePath,
        Integer startLine,
        Integer endLine,
        String excerpt,
        String extractionMethod,
        double confidence
) {
}
