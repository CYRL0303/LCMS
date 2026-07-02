package com.legacypilot.agenttool.endpoint.controller;

import com.legacypilot.agenttool.endpoint.dto.EndpointLookupRequest;
import com.legacypilot.agenttool.endpoint.dto.EndpointLookupResult;
import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.agenttool.endpoint.service.EndpointLookupService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Endpoint-related HTTP entry points for agent tools.
 */
@RestController
@RequestMapping("/api/agent/tools/endpoints")
public class EndpointToolController {
    private final AgentContextStore agentContextStore;
    private final EndpointLookupService endpointLookupService;

    public EndpointToolController(
            AgentContextStore agentContextStore,
            EndpointLookupService endpointLookupService
    ) {
        this.agentContextStore = agentContextStore;
        this.endpointLookupService = endpointLookupService;
    }

    @GetMapping
    public List<EndpointLookupResult> listCurrentEndpointContext() {
        return endpointLookupService.listEndpoints(agentContextStore.currentRepoId());
    }

    @PostMapping("/endpoint")
    public EndpointLookupResult getEndpointForDebug(@RequestBody EndpointLookupRequest request) {
        return endpointLookupService.findEndpoint(agentContextStore.currentRepoId(), request.path());
    }
}
