package com.legacypilot.agent.controller;

import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.agent.tool.graph.CodeGraphTool;
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
    private final AgentContextStore agentContextStore;
    private final CodeGraphTool codeGraphTool;

    public CodeGraphToolController(
            AgentContextStore agentContextStore,
            CodeGraphTool codeGraphTool
    ) {
        this.agentContextStore = agentContextStore;
        this.codeGraphTool = codeGraphTool;
    }

    @GetMapping("/graph")
    public CodeAnalysisResult getCurrentGraph() {
        return codeGraphTool.getGraph(agentContextStore.currentRepoId());
    }
}
