package com.legacypilot.agenttool.evidence.dto;

/**
 * Source evidence with a compact code snippet suitable for agent reasoning.
 */
public record EvidenceItemResult(
        String evidenceId,
        String filePath,
        Integer startLine,
        Integer endLine,
        String extractionMethod,
        double confidence,
        Integer snippetStartLine,
        Integer snippetEndLine,
        String codeSnippet
) {
}
