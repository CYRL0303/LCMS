package com.legacypilot.agent.service;

import com.legacypilot.agent.catalog.AgentToolCatalog;
import com.legacypilot.agent.catalog.AgentToolDefinition;
import com.legacypilot.agent.dto.chat.AgentChatRequest;
import com.legacypilot.agent.dto.chat.AgentChatResponse;
import com.legacypilot.agent.dto.chat.AgentToolDispatchResult;
import com.legacypilot.agent.model.AgentModelClient;
import com.legacypilot.agent.model.AgentModelRequest;
import com.legacypilot.agent.model.AgentModelResponse;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

/**
 * Experimental agent orchestrator that prepares tool context before model completion.
 */
@Service
public class LegacyPilotAgent {
    private final AgentContextStore agentContextStore;
    private final AgentToolDispatcherService agentToolDispatcherService;
    private final AgentModelClient modelClient;

    public LegacyPilotAgent(
            AgentContextStore agentContextStore,
            AgentToolDispatcherService agentToolDispatcherService,
            AgentModelClient modelClient
    ) {
        this.agentContextStore = agentContextStore;
        this.agentToolDispatcherService = agentToolDispatcherService;
        this.modelClient = modelClient;
    }

    public AgentChatResponse answer(AgentChatRequest request) {
        if (request == null || request.message() == null || request.message().isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "Agent message is required.");
        }

        String repoId = agentContextStore.currentRepoId();
        String userMessage = request.message().trim();
        List<AgentToolDefinition> availableTools = AgentToolCatalog.availableTools();

        AgentToolDispatchResult dispatchResult =
                agentToolDispatcherService.dispatch(userMessage, request.maxCandidates());

        AgentModelResponse modelResponse = modelClient.complete(new AgentModelRequest(
                repoId,
                userMessage,
                dispatchResult.agentContextText(),
                availableTools,
                dispatchResult.toolResults()
        ));

        return new AgentChatResponse(
                repoId,
                modelResponse.answer(),
                dispatchResult.query(),
                availableTools,
                dispatchResult.toolResults(),
                dispatchResult.agentContextText(),
                dispatchResult.investigation()
        );
    }
}
