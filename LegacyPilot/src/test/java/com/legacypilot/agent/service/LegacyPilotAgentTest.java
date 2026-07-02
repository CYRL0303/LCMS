package com.legacypilot.agent.service;

import com.legacypilot.agent.model.AgentModelClient;
import com.legacypilot.agent.model.AgentModelRequest;
import com.legacypilot.agent.model.AgentModelResponse;
import com.legacypilot.agent.tool.AgentToolResult;
import com.legacypilot.agent.tool.endpoint.EndpointLookupResult;
import com.legacypilot.agent.tool.endpoint.EndpointLookupTool;
import com.legacypilot.agent.tool.graph.CodeGraphTool;
import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.CodeGraphSummary;
import com.legacypilot.codeanalysis.service.CodeAnalysisResultStore;
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class LegacyPilotAgentTest {
    @Test
    void answerBuildsToolContextForQwenModelClient() {
        AgentContextStore contextStore = new AgentContextStore();
        contextStore.setCurrentRepoId("repo-1");
        CodeAnalysisResultStore resultStore = new CodeAnalysisResultStore();
        resultStore.save("repo-1", sampleResult());
        CapturingModelClient modelClient = new CapturingModelClient();
        LegacyPilotAgent agent = new LegacyPilotAgent(
                contextStore,
                new CodeGraphTool(resultStore),
                new EndpointLookupTool(resultStore),
                modelClient
        );

        AgentResponse response = agent.answer(new AgentRequest("Explain current endpoint risk", null));

        assertThat(response.repoId()).isEqualTo("repo-1");
        assertThat(response.answer()).isEqualTo("model answer");
        assertThat(response.toolResults()).extracting(AgentToolResult::toolName)
                .containsExactly("code_graph.get_graph", "endpoint.list");
        assertThat(response.availableTools()).extracting("name")
                .contains("code_graph.get_graph", "endpoint.lookup", "repository.context",
                        "incident.context", "evidence.lookup", "node.lookup", "rca.draft");
        assertThat(modelClient.lastRequest.repoId()).isEqualTo("repo-1");
        assertThat(modelClient.lastRequest.toolResults()).hasSize(2);
    }

    @Test
    void answerUsesEndpointLookupWhenEndpointPathProvided() {
        AgentContextStore contextStore = new AgentContextStore();
        contextStore.setCurrentRepoId("repo-1");
        CodeAnalysisResultStore resultStore = new CodeAnalysisResultStore();
        resultStore.save("repo-1", sampleResult());
        LegacyPilotAgent agent = new LegacyPilotAgent(
                contextStore,
                new CodeGraphTool(resultStore),
                new EndpointLookupTool(resultStore),
                new CapturingModelClient()
        );

        AgentResponse response = agent.answer(new AgentRequest("Trace this route", "api/orders//"));

        assertThat(response.toolResults()).extracting(AgentToolResult::toolName)
                .containsExactly("code_graph.get_graph", "endpoint.lookup");
        EndpointLookupResult endpoint = (EndpointLookupResult) response.toolResults().get(1).payload();
        assertThat(endpoint.path()).isEqualTo("/api/orders");
        assertThat(endpoint.controllerClass()).isEqualTo("OrderController");
    }

    private CodeAnalysisResult sampleResult() {
        CodeEndpoint endpoint = new CodeEndpoint(
                "endpoint-1",
                "GET",
                "/api/orders",
                "OrderController",
                "listOrders",
                "src/main/java/example/OrderController.java",
                42,
                List.of()
        );
        return new CodeAnalysisResult(
                new CodeGraphSummary("repo-1", "spring", 3, 2, 1, 1, 1),
                List.of(endpoint),
                List.of(),
                List.of(),
                List.of()
        );
    }

    private static class CapturingModelClient implements AgentModelClient {
        private AgentModelRequest lastRequest;

        @Override
        public AgentModelResponse complete(AgentModelRequest request) {
            this.lastRequest = request;
            return new AgentModelResponse("model answer");
        }
    }
}
