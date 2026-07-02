package com.legacypilot.agent.tool;

import java.util.List;

/**
 * Stable tool names exposed to the agent and future Qwen prompts.
 */
public final class AgentToolCatalog {
    public static final String CODE_GRAPH_GET_GRAPH = "code_graph.get_graph";
    public static final String ENDPOINT_LIST = "endpoint.list";
    public static final String ENDPOINT_LOOKUP = "endpoint.lookup";
    public static final String REPOSITORY_CONTEXT = "repository.context";
    public static final String INCIDENT_CONTEXT = "incident.context";
    public static final String EVIDENCE_LOOKUP = "evidence.lookup";
    public static final String NODE_LOOKUP = "node.lookup";
    public static final String RCA_DRAFT = "rca.draft";

    private static final List<AgentToolDefinition> AVAILABLE_TOOLS = List.of(
            new AgentToolDefinition(CODE_GRAPH_GET_GRAPH, "Read the current repository code graph.", true),
            new AgentToolDefinition(ENDPOINT_LIST, "List detected HTTP endpoints for the current repository.", true),
            new AgentToolDefinition(ENDPOINT_LOOKUP, "Resolve one HTTP endpoint to source evidence.", true),
            new AgentToolDefinition(REPOSITORY_CONTEXT, "Read repository metadata and file context.", false),
            new AgentToolDefinition(INCIDENT_CONTEXT, "Parse runtime errors, logs, and stack traces.", false),
            new AgentToolDefinition(EVIDENCE_LOOKUP, "Fetch source evidence bundles by evidence id.", false),
            new AgentToolDefinition(NODE_LOOKUP, "Search code graph nodes and symbols.", false),
            new AgentToolDefinition(RCA_DRAFT, "Draft and review root-cause analysis output.", false)
    );

    private AgentToolCatalog() {
    }

    public static List<AgentToolDefinition> availableTools() {
        return AVAILABLE_TOOLS;
    }
}
