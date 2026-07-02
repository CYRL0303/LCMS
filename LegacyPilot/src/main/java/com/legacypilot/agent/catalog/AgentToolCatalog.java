package com.legacypilot.agent.catalog;

import java.util.List;

/**
 * Stable tool names exposed to the agent and future Qwen prompts.
 */
public final class AgentToolCatalog {
    public static final String QUERY_UNDERSTAND = "query.understand";
    public static final String ENDPOINT_SELECT = "endpoint.select";
    public static final String ENDPOINT_LIST = "endpoint.list";
    public static final String ENDPOINT_LOOKUP = "endpoint.lookup";
    public static final String EVIDENCE_ENDPOINT = "evidence.endpoint";
    public static final String CODE_GRAPH_GET_GRAPH = "code_graph.get_graph";
    public static final String CONTEXT_BUILD = "context.build";
    public static final String RCA_INVESTIGATE = "rca.investigate";
    public static final String TRACE_METHOD_CALLS = "trace.method_calls";
    public static final String QWEN_COMPLETE = "qwen.complete";

    private static final List<AgentToolDefinition> AVAILABLE_TOOLS = List.of(
            new AgentToolDefinition(QUERY_UNDERSTAND, "Interpret user intent, target type, keywords, and search plan.", true),
            new AgentToolDefinition(ENDPOINT_SELECT, "Select likely endpoint candidates from analyzed project facts.", true),
            new AgentToolDefinition(ENDPOINT_LIST, "List detected HTTP endpoints for the current repository.", true),
            new AgentToolDefinition(ENDPOINT_LOOKUP, "Resolve one HTTP endpoint to source evidence references.", true),
            new AgentToolDefinition(EVIDENCE_ENDPOINT, "Fetch endpoint source evidence snippets.", true),
            new AgentToolDefinition(CODE_GRAPH_GET_GRAPH, "Read the current repository code graph.", true),
            new AgentToolDefinition(CONTEXT_BUILD, "Build compact agent-readable context from tool JSON.", true),
            new AgentToolDefinition(RCA_INVESTIGATE, "Run the current rule-based RCA investigation flow.", true),
            new AgentToolDefinition(TRACE_METHOD_CALLS, "Trace controller-service-repository method calls.", false),
            new AgentToolDefinition(QWEN_COMPLETE, "Ask Qwen to produce the final natural-language agent answer.", false)
    );

    private AgentToolCatalog() {
    }

    public static List<AgentToolDefinition> availableTools() {
        return AVAILABLE_TOOLS;
    }
}
