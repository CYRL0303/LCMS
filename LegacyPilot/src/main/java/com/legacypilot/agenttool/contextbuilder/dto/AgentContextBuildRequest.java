package com.legacypilot.agenttool.contextbuilder.dto;

/**
 * Debug request for building an agent-readable context from current project facts.
 */
public record AgentContextBuildRequest(
        String question,
        Integer maxCandidates
) {
}
