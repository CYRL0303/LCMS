package com.legacypilot.entity;

/**
 * Coarse workflow states for repository indexing and incident analysis.
 */
public enum AnalysisTaskStatus {
    /** Task exists but has not started. */
    PENDING,
    /** Repository source is being connected or indexed. */
    INDEXING_REPO,
    /** AI/RAG layer is collecting code, log, and memory evidence. */
    BUILDING_EVIDENCE,
    /** Qwen/RCA agents are generating a root-cause report. */
    GENERATING_RCA,
    /** Result is ready for human review/confirmation. */
    WAITING_REVIEW,
    /** Human confirmed the incident result. */
    CONFIRMED,
    /** Task failed and should expose an error message. */
    FAILED
}
