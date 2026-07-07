package com.legacypilot.agenttool.trace.controller;

import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.agenttool.trace.dto.EndpointTraceRequest;
import com.legacypilot.agenttool.trace.dto.EndpointTraceToolResult;
import com.legacypilot.agenttool.trace.service.EndpointTraceToolService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Trace-related HTTP entry points for agent tools.
 */
@RestController
@RequestMapping("/api/agent/tools/trace")
public class EndpointTraceToolController {
    private final AgentContextStore agentContextStore;
    private final EndpointTraceToolService endpointTraceToolService;

    public EndpointTraceToolController(
            AgentContextStore agentContextStore,
            EndpointTraceToolService endpointTraceToolService
    ) {
        this.agentContextStore = agentContextStore;
        this.endpointTraceToolService = endpointTraceToolService;
    }

    @PostMapping("/endpoint")
    public EndpointTraceToolResult traceEndpoint(@RequestBody EndpointTraceRequest request) {
        return endpointTraceToolService.traceEndpoint(agentContextStore.currentRepoId(), request);
    }
}
