package com.legacypilot.agent.service;

import com.legacypilot.agent.dto.rca.RcaEndpointCandidateResult;
import com.legacypilot.agent.dto.rca.RcaInvestigationRequest;
import com.legacypilot.agent.dto.rca.RcaInvestigationResult;
import com.legacypilot.agenttool.endpointselector.dto.EndpointCandidateResult;
import com.legacypilot.agenttool.endpointselector.dto.EndpointSelectionResult;
import com.legacypilot.agenttool.endpointselector.service.EndpointSelectorService;
import com.legacypilot.agenttool.evidence.dto.EndpointEvidenceResult;
import com.legacypilot.agenttool.evidence.service.EvidenceLookupService;
import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import com.legacypilot.agenttool.trace.dto.EndpointTraceRequest;
import com.legacypilot.agenttool.trace.dto.EndpointTraceToolResult;
import com.legacypilot.agenttool.trace.service.EndpointTraceToolService;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeNode;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * First-pass orchestration for connecting a user question to endpoint evidence.
 */
@Service
public class RcaInvestigationService {
    private static final int MAX_SNIPPET_CHARS = 700;

    private final AgentContextStore agentContextStore;
    private final EndpointSelectorService endpointSelectorService;
    private final EvidenceLookupService evidenceLookupService;
    private final EndpointTraceToolService endpointTraceToolService;

    public RcaInvestigationService(
            AgentContextStore agentContextStore,
            EndpointSelectorService endpointSelectorService,
            EvidenceLookupService evidenceLookupService,
            EndpointTraceToolService endpointTraceToolService
    ) {
        this.agentContextStore = agentContextStore;
        this.endpointSelectorService = endpointSelectorService;
        this.evidenceLookupService = evidenceLookupService;
        this.endpointTraceToolService = endpointTraceToolService;
    }

    public RcaInvestigationResult investigate(RcaInvestigationRequest request) {
        String repoId = agentContextStore.currentRepoId();
        EndpointSelectionResult selection = endpointSelectorService.select(
                repoId,
                request.question(),
                request.maxCandidates()
        );
        QueryUnderstandingResult understood = selection.query();
        List<RcaEndpointCandidateResult> candidates = selection.candidates().stream()
                .map(candidate -> toCandidateResult(repoId, candidate))
                .toList();

        return new RcaInvestigationResult(
                repoId,
                understood.rawQuestion(),
                understood,
                understood.keywords(),
                understood.searchPlan(),
                candidates,
                buildAgentContextText(repoId, understood, candidates),
                buildSummary(understood, candidates)
        );
    }

    private RcaEndpointCandidateResult toCandidateResult(String repoId, EndpointCandidateResult candidate) {
        EndpointEvidenceResult evidence =
                evidenceLookupService.getEndpointEvidence(repoId, candidate.endpoint().endpointId());
        EndpointTraceToolResult trace = endpointTraceToolService.traceEndpoint(
                repoId,
                new EndpointTraceRequest(candidate.endpoint().endpointId(), null, null, 6)
        );
        return new RcaEndpointCandidateResult(
                candidate.endpoint(),
                evidence,
                trace,
                candidate.score(),
                candidate.reason()
        );
    }

    private String buildAgentContextText(
            String repoId,
            QueryUnderstandingResult understood,
            List<RcaEndpointCandidateResult> candidates
    ) {
        StringBuilder builder = new StringBuilder();
        builder.append("RCA Agent Context").append(System.lineSeparator());
        builder.append("Repository: ").append(repoId).append(System.lineSeparator());
        builder.append("Question: ")
                .append(understood.rawQuestion().isBlank() ? "(empty)" : understood.rawQuestion())
                .append(System.lineSeparator());
        builder.append("Intent: ").append(understood.intent()).append(System.lineSeparator());
        builder.append("Target type: ").append(understood.targetType()).append(System.lineSeparator());
        builder.append("Keywords: ")
                .append(understood.keywords().isEmpty() ? "(none)" : String.join(", ", understood.keywords()))
                .append(System.lineSeparator());
        builder.append("Error signals: ")
                .append(understood.errorSignals().isEmpty() ? "(none)" : String.join(", ", understood.errorSignals()))
                .append(System.lineSeparator());
        builder.append("Search plan: ")
                .append(understood.searchPlan().isEmpty() ? "(none)" : String.join(" -> ", understood.searchPlan()))
                .append(System.lineSeparator())
                .append(System.lineSeparator());

        builder.append("Endpoint candidates and evidence:").append(System.lineSeparator());
        if (candidates.isEmpty()) {
            builder.append("- No endpoint candidates were selected.").append(System.lineSeparator());
            return builder.toString();
        }

        for (int index = 0; index < candidates.size(); index++) {
            RcaEndpointCandidateResult candidate = candidates.get(index);
            builder.append(index + 1)
                    .append(". ")
                    .append(candidate.endpoint().httpMethod())
                    .append(" ")
                    .append(candidate.endpoint().path())
                    .append(System.lineSeparator());
            builder.append("   Handler: ")
                    .append(candidate.endpoint().controllerClass())
                    .append(".")
                    .append(candidate.endpoint().handlerMethod())
                    .append(System.lineSeparator());
            builder.append("   Source: ")
                    .append(candidate.endpoint().filePath())
                    .append(":")
                    .append(candidate.endpoint().lineNumber())
                    .append(System.lineSeparator());
            builder.append("   Match: ")
                    .append(candidate.reason())
                    .append(" (score=")
                    .append(candidate.score())
                    .append(")")
                    .append(System.lineSeparator());
            builder.append("   Evidence snippets:").append(System.lineSeparator());
            candidate.evidence().items().forEach(item -> {
                builder.append("   - ")
                        .append(item.extractionMethod())
                        .append(" confidence=")
                        .append(item.confidence())
                        .append(" lines=")
                        .append(item.snippetStartLine())
                        .append("-")
                        .append(item.snippetEndLine())
                        .append(System.lineSeparator());
                builder.append("     ")
                        .append(trimSnippet(item.codeSnippet()).replace(System.lineSeparator(), System.lineSeparator() + "     "))
                        .append(System.lineSeparator());
            });
            appendTraceSummary(builder, candidate.trace());
        }
        return builder.toString();
    }

    private void appendTraceSummary(StringBuilder builder, EndpointTraceToolResult trace) {
        builder.append("   Trace:").append(System.lineSeparator());
        builder.append("   - matchedNodes=")
                .append(trace.matchedNodes().size())
                .append(", matchedEdges=")
                .append(trace.matchedEdges().size())
                .append(", graphPaths=")
                .append(trace.graphPaths().size())
                .append(System.lineSeparator());
        if (trace.matchedEdges().isEmpty()) {
            builder.append("   - No downstream CALLS edge was found from this endpoint handler.")
                    .append(System.lineSeparator());
            return;
        }
        for (CodeEdge edge : trace.matchedEdges()) {
            builder.append("   - ")
                    .append(labelForNode(trace, edge.sourceNodeId()))
                    .append(" --")
                    .append(edge.type())
                    .append("--> ")
                    .append(labelForNode(trace, edge.targetNodeId()))
                    .append(System.lineSeparator());
        }
    }

    private String labelForNode(EndpointTraceToolResult trace, String nodeId) {
        return trace.matchedNodes().stream()
                .filter(node -> node.nodeId().equals(nodeId))
                .findFirst()
                .map(this::nodeLabel)
                .orElse(nodeId);
    }

    private String nodeLabel(CodeNode node) {
        return node.type() + ":" + node.name();
    }

    private String buildSummary(
            QueryUnderstandingResult understood,
            List<RcaEndpointCandidateResult> candidates
    ) {
        StringBuilder builder = new StringBuilder();
        builder.append("Question: ")
                .append(understood.rawQuestion().isBlank() ? "(empty)" : understood.rawQuestion())
                .append(System.lineSeparator());
        builder.append("Intent: ").append(understood.intent()).append(System.lineSeparator());
        builder.append("Target type: ").append(understood.targetType()).append(System.lineSeparator());
        builder.append("Extracted keywords: ")
                .append(understood.keywords().isEmpty() ? "(none)" : String.join(", ", understood.keywords()))
                .append(System.lineSeparator());
        builder.append("Error signals: ")
                .append(understood.errorSignals().isEmpty() ? "(none)" : String.join(", ", understood.errorSignals()))
                .append(System.lineSeparator());
        builder.append("Search plan: ")
                .append(understood.searchPlan().isEmpty() ? "(none)" : String.join(" -> ", understood.searchPlan()))
                .append(System.lineSeparator());
        builder.append("Candidate endpoints:").append(System.lineSeparator());
        for (RcaEndpointCandidateResult candidate : candidates) {
            builder.append("- ")
                    .append(candidate.endpoint().httpMethod())
                    .append(" ")
                    .append(candidate.endpoint().path())
                    .append(" -> ")
                    .append(candidate.endpoint().controllerClass())
                    .append(".")
                    .append(candidate.endpoint().handlerMethod())
                    .append(" (score=")
                    .append(candidate.score())
                    .append(", evidenceItems=")
                    .append(candidate.evidence().items().size())
                    .append(", traceEdges=")
                    .append(candidate.trace().matchedEdges().size())
                    .append(")")
                    .append(System.lineSeparator());
        }
        return builder.toString();
    }

    private String trimSnippet(String snippet) {
        if (snippet == null || snippet.isBlank()) {
            return "(no source snippet available)";
        }
        String normalized = snippet.strip();
        if (normalized.length() <= MAX_SNIPPET_CHARS) {
            return normalized;
        }
        return normalized.substring(0, MAX_SNIPPET_CHARS) + "...";
    }
}
