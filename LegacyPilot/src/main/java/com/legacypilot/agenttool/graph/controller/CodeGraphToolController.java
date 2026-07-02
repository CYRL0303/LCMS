package com.legacypilot.agenttool.graph.controller;

import com.legacypilot.agenttool.graph.dto.CodeGraphResult;
import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.agenttool.graph.service.CodeGraphService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Code-graph HTTP entry points for agent tools.
 */
@RestController
@RequestMapping("/api/agent/tools/code-graph")
public class CodeGraphToolController {
    private final AgentContextStore agentContextStore;
    private final CodeGraphService codeGraphService;

    public CodeGraphToolController(
            AgentContextStore agentContextStore,
            CodeGraphService codeGraphService
    ) {
        this.agentContextStore = agentContextStore;
        this.codeGraphService = codeGraphService;
    }

    @GetMapping("/graph")
    public CodeGraphResult getCurrentGraph() {
        return codeGraphService.getGraph(agentContextStore.currentRepoId());
    }
}
