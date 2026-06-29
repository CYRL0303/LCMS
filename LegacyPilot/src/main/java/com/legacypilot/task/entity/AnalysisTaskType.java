package com.legacypilot.task.entity;

/**
 * Distinguishes the two first-class backend task kinds.
 */
public enum AnalysisTaskType {
    /** Work that prepares a repository for code graph/RAG queries. */
    REPO_INDEX,
    /** Work that investigates one incident against a connected repository. */
    INCIDENT_ANALYSIS
}
