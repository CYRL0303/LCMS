package com.legacypilot.agent.controller;

import com.legacypilot.agent.service.AgentCurrentCodeAnalysisService;
import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Code-graph HTTP entry points for agent tools.
 */
@RestController
@RequestMapping("/api/agent/tools/code-graph")
public class CodeGraphToolController {
    private final AgentCurrentCodeAnalysisService agentCurrentCodeAnalysisService;

    public CodeGraphToolController(AgentCurrentCodeAnalysisService agentCurrentCodeAnalysisService) {
        this.agentCurrentCodeAnalysisService = agentCurrentCodeAnalysisService;
    }

    @GetMapping("/graph")
    public CodeAnalysisResult getCurrentGraph() {
        return agentCurrentCodeAnalysisService.currentGraph();
    }
}
