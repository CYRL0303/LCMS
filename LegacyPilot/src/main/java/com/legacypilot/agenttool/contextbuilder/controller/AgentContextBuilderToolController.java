package com.legacypilot.agenttool.contextbuilder.controller;

import com.legacypilot.agenttool.contextbuilder.dto.AgentContextBuildRequest;
import com.legacypilot.agenttool.contextbuilder.dto.AgentContextBuildResult;
import com.legacypilot.agenttool.contextbuilder.service.AgentContextBuilderService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Debug controller for building agent-readable context before Qwen integration.
 */
@RestController
@RequestMapping("/api/agent/tools/context-builder")
public class AgentContextBuilderToolController {
    private final AgentContextBuilderService agentContextBuilderService;

    public AgentContextBuilderToolController(AgentContextBuilderService agentContextBuilderService) {
        this.agentContextBuilderService = agentContextBuilderService;
    }

    @PostMapping("/build")
    public AgentContextBuildResult build(@RequestBody AgentContextBuildRequest request) {
        return agentContextBuilderService.buildCurrent(request.question(), request.maxCandidates());
    }
}
