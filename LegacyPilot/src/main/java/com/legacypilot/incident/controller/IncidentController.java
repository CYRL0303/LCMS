package com.legacypilot.incident.controller;

import com.legacypilot.incident.dto.AnalyzeIncidentRequest;
import com.legacypilot.incident.dto.ConfirmIncidentRequest;
import com.legacypilot.incident.service.IncidentService;
import com.legacypilot.task.entity.AnalysisTask;
import com.legacypilot.incident.entity.IncidentRecord;
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
    private final IncidentService incidentService;

    public IncidentController(IncidentService incidentService) {
        this.incidentService = incidentService;
    }

    /**
     * Creates an incident analysis task from a raw log/stack trace. Current MVP
     * behavior records the task and incident only; evidence/RCA generation is a
     * later AI-service integration point.
     */
    @PostMapping("/incidents/analyze")
    public AnalysisTask analyzeIncident(@RequestBody AnalyzeIncidentRequest request) {
        return incidentService.analyzeIncident(request);
    }

    /**
     * Returns the stored incident record for review/debugging.
     */
    @GetMapping("/incidents/{incidentId}")
    public IncidentRecord getIncident(@PathVariable String incidentId) {
        return incidentService.getIncident(incidentId);
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
        return incidentService.confirmIncident(incidentId, request);
    }
}
