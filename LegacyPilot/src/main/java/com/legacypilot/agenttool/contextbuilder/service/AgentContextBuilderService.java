package com.legacypilot.agenttool.contextbuilder.service;

import com.legacypilot.agenttool.contextbuilder.dto.AgentContextBuildResult;
import com.legacypilot.agenttool.contextbuilder.dto.AgentEndpointContextItem;
import com.legacypilot.agenttool.endpoint.dto.EndpointLookupResult;
import com.legacypilot.agenttool.endpointselector.dto.EndpointCandidateResult;
import com.legacypilot.agenttool.endpointselector.dto.EndpointSelectionResult;
import com.legacypilot.agenttool.endpointselector.service.EndpointSelectorService;
import com.legacypilot.agenttool.evidence.dto.EndpointEvidenceResult;
import com.legacypilot.agenttool.evidence.dto.EvidenceItemResult;
import com.legacypilot.agenttool.evidence.service.EvidenceLookupService;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Tool service that compresses multiple JSON facts into agent-readable context.
 */
@Service
public class AgentContextBuilderService {
    private static final Logger log = LoggerFactory.getLogger(AgentContextBuilderService.class);
    private static final int MAX_SNIPPET_CHARS = 700;

    private final EndpointSelectorService endpointSelectorService;
    private final EvidenceLookupService evidenceLookupService;

    public AgentContextBuilderService(
            EndpointSelectorService endpointSelectorService,
            EvidenceLookupService evidenceLookupService
    ) {
        this.endpointSelectorService = endpointSelectorService;
        this.evidenceLookupService = evidenceLookupService;
    }

    public AgentContextBuildResult buildCurrent(String question, Integer maxCandidates) {
        EndpointSelectionResult selection = endpointSelectorService.selectCurrent(question, maxCandidates);
        List<AgentEndpointContextItem> contexts = selection.candidates().stream()
                .map(candidate -> toContextItem(selection.repoId(), candidate))
                .toList();
        String text = buildText(selection, contexts);

        log.info("Agent context built: repoId={}, endpointContextCount={}, textChars={}",
                selection.repoId(),
                contexts.size(),
                text.length()
        );
        return new AgentContextBuildResult(
                selection.repoId(),
                selection.question(),
                selection.query(),
                contexts,
                text
        );
    }

    private AgentEndpointContextItem toContextItem(String repoId, EndpointCandidateResult candidate) {
        EndpointEvidenceResult evidence =
                evidenceLookupService.getEndpointEvidence(repoId, candidate.endpoint().endpointId());
        return new AgentEndpointContextItem(
                candidate.endpoint(),
                evidence,
                candidate.score(),
                candidate.reason()
        );
    }

    private String buildText(EndpointSelectionResult selection, List<AgentEndpointContextItem> contexts) {
        StringBuilder builder = new StringBuilder();
        builder.append("RCA investigation context").append(System.lineSeparator());
        builder.append("Repository: ").append(selection.repoId()).append(System.lineSeparator());
        builder.append("User question: ").append(blankToPlaceholder(selection.question())).append(System.lineSeparator());
        builder.append("Intent: ").append(selection.query().intent()).append(System.lineSeparator());
        builder.append("Target type: ").append(selection.query().targetType()).append(System.lineSeparator());
        builder.append("Keywords: ").append(joinOrNone(selection.query().keywords())).append(System.lineSeparator());
        builder.append("Error signals: ").append(joinOrNone(selection.query().errorSignals())).append(System.lineSeparator());
        builder.append(System.lineSeparator());
        builder.append("Selected endpoints:").append(System.lineSeparator());

        if (contexts.isEmpty()) {
            builder.append("- No endpoint candidate was selected.").append(System.lineSeparator());
            return builder.toString();
        }

        for (int index = 0; index < contexts.size(); index++) {
            appendEndpointContext(builder, index + 1, contexts.get(index));
        }
        return builder.toString();
    }

    private void appendEndpointContext(StringBuilder builder, int index, AgentEndpointContextItem context) {
        EndpointLookupResult endpoint = context.endpoint();
        builder.append(index)
                .append(". ")
                .append(endpoint.httpMethod())
                .append(" ")
                .append(endpoint.path())
                .append(System.lineSeparator());
        builder.append("   Handler: ")
                .append(endpoint.controllerClass())
                .append(".")
                .append(endpoint.handlerMethod())
                .append(System.lineSeparator());
        builder.append("   Source: ")
                .append(endpoint.filePath())
                .append(":")
                .append(endpoint.lineNumber())
                .append(System.lineSeparator());
        builder.append("   Selection reason: ")
                .append(context.reason())
                .append(" (score=")
                .append(context.score())
                .append(")")
                .append(System.lineSeparator());
        builder.append("   Evidence:").append(System.lineSeparator());
        for (EvidenceItemResult item : context.evidence().items()) {
            builder.append("   - ")
                    .append(item.extractionMethod())
                    .append(" confidence=")
                    .append(item.confidence())
                    .append(" lines=")
                    .append(item.snippetStartLine())
                    .append("-")
                    .append(item.snippetEndLine())
                    .append(System.lineSeparator());
            builder.append(indentSnippet(trimSnippet(item.codeSnippet()))).append(System.lineSeparator());
        }
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

    private String indentSnippet(String snippet) {
        return "     " + snippet.replace(System.lineSeparator(), System.lineSeparator() + "     ");
    }

    private String joinOrNone(List<String> values) {
        if (values == null || values.isEmpty()) {
            return "(none)";
        }
        return String.join(", ", values);
    }

    private String blankToPlaceholder(String value) {
        return value == null || value.isBlank() ? "(empty)" : value;
    }
}
