package com.legacypilot.agent.service;

import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.service.CodeAnalysisResultStore;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * Reads code-analysis context for the current agent workspace.
 */
@Service
public class AgentCurrentCodeAnalysisService {
    private final AgentContextStore agentContextStore;
    private final CodeAnalysisResultStore codeAnalysisResultStore;

    public AgentCurrentCodeAnalysisService(
            AgentContextStore agentContextStore,
            CodeAnalysisResultStore codeAnalysisResultStore
    ) {
        this.agentContextStore = agentContextStore;
        this.codeAnalysisResultStore = codeAnalysisResultStore;
    }

    public CodeAnalysisResult currentGraph() {
        return codeAnalysisResultStore.get(agentContextStore.currentRepoId());
    }

    public List<CodeEndpoint> currentEndpoints() {
        return currentGraph().endpoints();
    }
}
