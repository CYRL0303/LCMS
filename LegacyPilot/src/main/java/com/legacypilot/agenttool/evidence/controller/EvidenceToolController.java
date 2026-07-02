package com.legacypilot.agenttool.evidence.controller;

import com.legacypilot.agenttool.evidence.dto.EndpointEvidenceRequest;
import com.legacypilot.agenttool.evidence.dto.EndpointEvidenceResult;
import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.agenttool.evidence.service.EvidenceLookupService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Evidence-related HTTP entry points for agent tools.
 */
@RestController
@RequestMapping("/api/agent/tools/evidence")
public class EvidenceToolController {
    private final AgentContextStore agentContextStore;
    private final EvidenceLookupService evidenceLookupService;

    public EvidenceToolController(
            AgentContextStore agentContextStore,
            EvidenceLookupService evidenceLookupService
    ) {
        this.agentContextStore = agentContextStore;
        this.evidenceLookupService = evidenceLookupService;
    }

    @PostMapping("/endpoint")
    public EndpointEvidenceResult getEndpointEvidence(@RequestBody EndpointEvidenceRequest request) {
        return evidenceLookupService.getEndpointEvidence(agentContextStore.currentRepoId(), request.endpointId());
    }
}
