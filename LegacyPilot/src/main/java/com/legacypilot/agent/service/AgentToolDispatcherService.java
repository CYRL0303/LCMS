package com.legacypilot.agent.service;

import com.legacypilot.agent.catalog.AgentToolCatalog;
import com.legacypilot.agent.catalog.AgentToolResult;
import com.legacypilot.agent.dto.chat.AgentToolDispatchResult;
import com.legacypilot.agent.dto.rca.RcaInvestigationRequest;
import com.legacypilot.agent.dto.rca.RcaInvestigationResult;
import com.legacypilot.agenttool.endpoint.dto.EndpointLookupResult;
import com.legacypilot.agenttool.endpoint.service.EndpointLookupService;
import com.legacypilot.agenttool.graph.dto.CodeGraphResult;
import com.legacypilot.agenttool.graph.service.CodeGraphService;
import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import com.legacypilot.agenttool.query.service.QueryUnderstandingService;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Rule-based dispatcher that chooses agent tools from natural-language intent.
 */
@Service
public class AgentToolDispatcherService {
    private static final Logger log = LoggerFactory.getLogger(AgentToolDispatcherService.class);

    private final AgentContextStore agentContextStore;
    private final QueryUnderstandingService queryUnderstandingService;
    private final RcaInvestigationService rcaInvestigationService;
    private final EndpointLookupService endpointLookupService;
    private final CodeGraphService codeGraphService;

    public AgentToolDispatcherService(
            AgentContextStore agentContextStore,
            QueryUnderstandingService queryUnderstandingService,
            RcaInvestigationService rcaInvestigationService,
            EndpointLookupService endpointLookupService,
            CodeGraphService codeGraphService
    ) {
        this.agentContextStore = agentContextStore;
        this.queryUnderstandingService = queryUnderstandingService;
        this.rcaInvestigationService = rcaInvestigationService;
        this.endpointLookupService = endpointLookupService;
        this.codeGraphService = codeGraphService;
    }

    public AgentToolDispatchResult dispatch(String message, Integer maxCandidates) {
        String repoId = agentContextStore.currentRepoId();
        QueryUnderstandingResult query = queryUnderstandingService.understand(message);
        log.info("Agent规则调度开始：repoId={}，intent={}，targetType={}，searchPlan={}",
                repoId,
                query.intent(),
                query.targetType(),
                query.searchPlan()
        );

        return switch (query.intent()) {
            case "RCA" -> dispatchRca(repoId, message, maxCandidates, query);
            case "EXPLORE_ENDPOINT" -> dispatchEndpointExplore(repoId, query);
            case "EXPLORE_GRAPH" -> dispatchGraphExplore(repoId, query);
            case "SUMMARIZE_PROJECT" -> dispatchProjectSummary(repoId, query);
            case "LOOKUP_CODE" -> dispatchNotImplemented(repoId, query, AgentToolCatalog.TRACE_METHOD_CALLS,
                    "Code symbol lookup is not implemented yet. The next step is to add node/symbol lookup over codeanalysis results.");
            default -> dispatchNotImplemented(repoId, query, "agent.clarify",
                    "The request could not be mapped to an implemented tool. Ask a more specific project, endpoint, graph, or RCA question.");
        };
    }

    private AgentToolDispatchResult dispatchRca(
            String repoId,
            String message,
            Integer maxCandidates,
            QueryUnderstandingResult query
    ) {
        RcaInvestigationResult investigation = rcaInvestigationService.investigate(
                new RcaInvestigationRequest(message, maxCandidates)
        );
        List<AgentToolResult> toolResults = List.of(
                new AgentToolResult(AgentToolCatalog.QUERY_UNDERSTAND, query),
                new AgentToolResult(AgentToolCatalog.RCA_INVESTIGATE, investigation),
                new AgentToolResult(AgentToolCatalog.CONTEXT_BUILD, investigation.agentContextText())
        );
        return new AgentToolDispatchResult(
                repoId,
                query,
                toolResults,
                investigation.agentContextText(),
                investigation
        );
    }

    private AgentToolDispatchResult dispatchEndpointExplore(String repoId, QueryUnderstandingResult query) {
        List<EndpointLookupResult> endpoints = endpointLookupService.listEndpoints(repoId);
        List<AgentToolResult> toolResults = List.of(
                new AgentToolResult(AgentToolCatalog.QUERY_UNDERSTAND, query),
                new AgentToolResult(AgentToolCatalog.ENDPOINT_LIST, endpoints)
        );
        return new AgentToolDispatchResult(
                repoId,
                query,
                toolResults,
                buildEndpointSummary(repoId, query, endpoints),
                null
        );
    }

    private AgentToolDispatchResult dispatchGraphExplore(String repoId, QueryUnderstandingResult query) {
        CodeGraphResult graph = codeGraphService.getGraph(repoId);
        List<AgentToolResult> toolResults = List.of(
                new AgentToolResult(AgentToolCatalog.QUERY_UNDERSTAND, query),
                new AgentToolResult(AgentToolCatalog.CODE_GRAPH_GET_GRAPH, graph)
        );
        return new AgentToolDispatchResult(
                repoId,
                query,
                toolResults,
                buildGraphSummary(repoId, query, graph),
                null
        );
    }

    private AgentToolDispatchResult dispatchProjectSummary(String repoId, QueryUnderstandingResult query) {
        CodeGraphResult graph = codeGraphService.getGraph(repoId);
        List<EndpointLookupResult> endpoints = endpointLookupService.listEndpoints(repoId);
        List<AgentToolResult> toolResults = List.of(
                new AgentToolResult(AgentToolCatalog.QUERY_UNDERSTAND, query),
                new AgentToolResult(AgentToolCatalog.CODE_GRAPH_GET_GRAPH, graph),
                new AgentToolResult(AgentToolCatalog.ENDPOINT_LIST, endpoints)
        );
        return new AgentToolDispatchResult(
                repoId,
                query,
                toolResults,
                buildProjectSummary(repoId, query, graph, endpoints),
                null
        );
    }

    private AgentToolDispatchResult dispatchNotImplemented(
            String repoId,
            QueryUnderstandingResult query,
            String toolName,
            String message
    ) {
        List<AgentToolResult> toolResults = List.of(
                new AgentToolResult(AgentToolCatalog.QUERY_UNDERSTAND, query),
                new AgentToolResult(toolName, message)
        );
        return new AgentToolDispatchResult(
                repoId,
                query,
                toolResults,
                buildBasicContext(repoId, query, message),
                null
        );
    }

    private String buildEndpointSummary(
            String repoId,
            QueryUnderstandingResult query,
            List<EndpointLookupResult> endpoints
    ) {
        StringBuilder builder = baseContext(repoId, query);
        builder.append("Detected endpoints: ").append(endpoints.size()).append(System.lineSeparator());
        for (EndpointLookupResult endpoint : endpoints) {
            builder.append("- ")
                    .append(endpoint.httpMethod())
                    .append(" ")
                    .append(endpoint.path())
                    .append(" -> ")
                    .append(endpoint.controllerClass())
                    .append(".")
                    .append(endpoint.handlerMethod())
                    .append(System.lineSeparator());
        }
        return builder.toString();
    }

    private String buildGraphSummary(String repoId, QueryUnderstandingResult query, CodeGraphResult graph) {
        StringBuilder builder = baseContext(repoId, query);
        builder.append("Code graph summary:").append(System.lineSeparator());
        builder.append("- projectType: ").append(graph.summary().projectType()).append(System.lineSeparator());
        builder.append("- nodeCount: ").append(graph.summary().nodeCount()).append(System.lineSeparator());
        builder.append("- edgeCount: ").append(graph.summary().edgeCount()).append(System.lineSeparator());
        builder.append("- endpointCount: ").append(graph.summary().endpointCount()).append(System.lineSeparator());
        builder.append("- evidenceCount: ").append(graph.evidenceRefs().size()).append(System.lineSeparator());
        return builder.toString();
    }

    private String buildProjectSummary(
            String repoId,
            QueryUnderstandingResult query,
            CodeGraphResult graph,
            List<EndpointLookupResult> endpoints
    ) {
        StringBuilder builder = new StringBuilder(buildGraphSummary(repoId, query, graph));
        builder.append(System.lineSeparator());
        builder.append("Endpoint overview:").append(System.lineSeparator());
        for (EndpointLookupResult endpoint : endpoints) {
            builder.append("- ")
                    .append(endpoint.httpMethod())
                    .append(" ")
                    .append(endpoint.path())
                    .append(System.lineSeparator());
        }
        return builder.toString();
    }

    private String buildBasicContext(String repoId, QueryUnderstandingResult query, String message) {
        return baseContext(repoId, query)
                .append(message)
                .append(System.lineSeparator())
                .toString();
    }

    private StringBuilder baseContext(String repoId, QueryUnderstandingResult query) {
        StringBuilder builder = new StringBuilder();
        builder.append("Agent dispatch context").append(System.lineSeparator());
        builder.append("Repository: ").append(repoId).append(System.lineSeparator());
        builder.append("Question: ").append(query.rawQuestion()).append(System.lineSeparator());
        builder.append("Intent: ").append(query.intent()).append(System.lineSeparator());
        builder.append("Target type: ").append(query.targetType()).append(System.lineSeparator());
        builder.append("Keywords: ").append(joinOrNone(query.keywords())).append(System.lineSeparator());
        builder.append("Error signals: ").append(joinOrNone(query.errorSignals())).append(System.lineSeparator());
        builder.append("Search plan: ").append(joinOrNone(query.searchPlan())).append(System.lineSeparator());
        builder.append(System.lineSeparator());
        return builder;
    }

    private String joinOrNone(List<String> values) {
        if (values == null || values.isEmpty()) {
            return "(none)";
        }
        return String.join(", ", new ArrayList<>(values));
    }
}
