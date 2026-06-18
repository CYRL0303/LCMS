package com.legacypilot.controller;

import com.legacypilot.dto.AnalyzeIncidentRequest;
import com.legacypilot.dto.ConfirmIncidentRequest;
import com.legacypilot.entity.AnalysisTask;
import com.legacypilot.entity.IncidentRecord;
import com.legacypilot.service.AnalysisService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Incident analysis, review, and confirmation endpoints.
 */
@RestController
@RequestMapping("/api")
public class IncidentController {
    private final AnalysisService analysisService;

    public IncidentController(AnalysisService analysisService) {
        this.analysisService = analysisService;
    }

    /**
     * Creates an incident analysis task from a raw log/stack trace. Current MVP
     * behavior records the task and incident only; evidence/RCA generation is a
     * later AI-service integration point.
     */
    @PostMapping("/incidents/analyze")
    public AnalysisTask analyzeIncident(@RequestBody AnalyzeIncidentRequest request) {
        return analysisService.analyzeIncident(request);
    }

    /**
     * Returns the stored incident record for review/debugging.
     */
    @GetMapping("/incidents/{incidentId}")
    public IncidentRecord getIncident(@PathVariable String incidentId) {
        return analysisService.getIncident(incidentId);
    }

    /**
     * Marks an incident as user-confirmed. This mirrors the future rule that
     * only human-confirmed RCA results may be saved as long-term incident memory.
     */
    @PostMapping("/incidents/{incidentId}/confirm")
    public IncidentRecord confirmIncident(
            @PathVariable String incidentId,
            @RequestBody ConfirmIncidentRequest request
    ) {
        return analysisService.confirmIncident(incidentId, request);
    }
}
