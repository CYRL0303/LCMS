package com.legacypilot.agent.service;

import com.legacypilot.agent.model.AgentModelClient;
import com.legacypilot.agent.model.AgentModelRequest;
import com.legacypilot.agent.model.AgentModelResponse;
import com.legacypilot.agent.tool.AgentToolCatalog;
import com.legacypilot.agent.tool.AgentToolDefinition;
import com.legacypilot.agent.tool.AgentToolResult;
import com.legacypilot.agent.tool.endpoint.EndpointLookupTool;
import com.legacypilot.agent.tool.graph.CodeGraphTool;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

/**
 * Thin agent orchestrator that gathers tool context before model completion.
 */
@Service
public class LegacyPilotAgent {
    private final AgentContextStore agentContextStore;
    private final CodeGraphTool codeGraphTool;
    private final EndpointLookupTool endpointLookupTool;
    private final AgentModelClient modelClient;

    public LegacyPilotAgent(
            AgentContextStore agentContextStore,
            CodeGraphTool codeGraphTool,
            EndpointLookupTool endpointLookupTool,
            AgentModelClient modelClient
    ) {
        this.agentContextStore = agentContextStore;
        this.codeGraphTool = codeGraphTool;
        this.endpointLookupTool = endpointLookupTool;
        this.modelClient = modelClient;
    }

    public AgentResponse answer(AgentRequest request) {
        if (request == null || request.message() == null || request.message().isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "Agent message is required.");
        }

        String repoId = agentContextStore.currentRepoId();
        String userMessage = request.message().trim();
        List<AgentToolDefinition> availableTools = AgentToolCatalog.availableTools();
        List<AgentToolResult> toolResults = new ArrayList<>();

        toolResults.add(new AgentToolResult(
                AgentToolCatalog.CODE_GRAPH_GET_GRAPH,
                codeGraphTool.getGraph(repoId)
        ));

        if (hasText(request.endpointPath())) {
            toolResults.add(new AgentToolResult(
                    AgentToolCatalog.ENDPOINT_LOOKUP,
                    endpointLookupTool.findEndpoint(repoId, request.endpointPath())
            ));
        } else {
            toolResults.add(new AgentToolResult(
                    AgentToolCatalog.ENDPOINT_LIST,
                    endpointLookupTool.listEndpoints(repoId)
            ));
        }

        List<AgentToolResult> immutableToolResults = List.copyOf(toolResults);
        AgentModelResponse modelResponse = modelClient.complete(new AgentModelRequest(
                repoId,
                userMessage,
                availableTools,
                immutableToolResults
        ));

        return new AgentResponse(
                repoId,
                modelResponse.answer(),
                availableTools,
                immutableToolResults
        );
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
