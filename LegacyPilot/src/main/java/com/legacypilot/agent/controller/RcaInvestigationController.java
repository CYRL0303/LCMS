package com.legacypilot.agent.controller;

import com.legacypilot.agent.dto.rca.RcaInvestigationRequest;
import com.legacypilot.agent.dto.rca.RcaInvestigationResult;
import com.legacypilot.agent.service.RcaInvestigationService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Temporary RCA investigation endpoint that orchestrates existing agent tools.
 */
@RestController
@RequestMapping("/api/agent/rca")
public class RcaInvestigationController {
    private final RcaInvestigationService rcaInvestigationService;

    public RcaInvestigationController(RcaInvestigationService rcaInvestigationService) {
        this.rcaInvestigationService = rcaInvestigationService;
    }

    @PostMapping("/investigate")
    public RcaInvestigationResult investigate(@RequestBody RcaInvestigationRequest request) {
        return rcaInvestigationService.investigate(request);
    }
}
