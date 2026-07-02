package com.legacypilot.agenttool.query.dto;

import java.util.List;

/**
 * Structured interpretation of a user investigation question.
 */
public record QueryUnderstandingResult(
        String rawQuestion,
        String intent,
        String targetType,
        List<String> keywords,
        List<String> errorSignals,
        List<String> searchPlan
) {
}
