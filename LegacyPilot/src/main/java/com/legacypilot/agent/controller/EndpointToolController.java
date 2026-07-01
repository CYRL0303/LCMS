package com.legacypilot.agent.controller;

import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.agent.tool.endpoint.EndpointLookupRequest;
import com.legacypilot.agent.tool.endpoint.EndpointLookupResult;
import com.legacypilot.agent.tool.endpoint.EndpointLookupTool;
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
    private final EndpointLookupTool endpointLookupTool;

    public EndpointToolController(
            AgentContextStore agentContextStore,
            EndpointLookupTool endpointLookupTool
    ) {
        this.agentContextStore = agentContextStore;
        this.endpointLookupTool = endpointLookupTool;
    }

    @GetMapping
    public List<EndpointLookupResult> listCurrentEndpointContext() {
        return endpointLookupTool.listEndpoints(agentContextStore.currentRepoId());
    }

    @PostMapping("/endpoint")
    public EndpointLookupResult getEndpointForDebug(@RequestBody EndpointLookupRequest request) {
        return endpointLookupTool.findEndpoint(agentContextStore.currentRepoId(), request.path());
    }
}
