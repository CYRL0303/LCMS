package com.legacypilot.agenttool.endpointselector.service;

import com.legacypilot.agent.service.AgentContextStore;
import com.legacypilot.agenttool.endpoint.dto.EndpointLookupResult;
import com.legacypilot.agenttool.endpoint.service.EndpointLookupService;
import com.legacypilot.agenttool.endpointselector.dto.EndpointCandidateResult;
import com.legacypilot.agenttool.endpointselector.dto.EndpointSelectionResult;
import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import com.legacypilot.agenttool.query.service.QueryUnderstandingService;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Tool service that selects likely endpoint candidates from code-analysis facts.
 */
@Service
public class EndpointSelectorService {
    private static final Logger log = LoggerFactory.getLogger(EndpointSelectorService.class);
    private static final int DEFAULT_MAX_CANDIDATES = 3;
    private static final Set<String> ERROR_SIGNAL_WORDS = Set.of(
            "400", "401", "403", "404", "409", "422", "429", "500", "502", "503",
            "timeout", "timedout", "nullpointer", "npe", "exception", "badrequest",
            "notfound", "unauthorized", "forbidden", "crash", "超时", "异常", "空指针"
    );

    private final AgentContextStore agentContextStore;
    private final QueryUnderstandingService queryUnderstandingService;
    private final EndpointLookupService endpointLookupService;

    public EndpointSelectorService(
            AgentContextStore agentContextStore,
            QueryUnderstandingService queryUnderstandingService,
            EndpointLookupService endpointLookupService
    ) {
        this.agentContextStore = agentContextStore;
        this.queryUnderstandingService = queryUnderstandingService;
        this.endpointLookupService = endpointLookupService;
    }

    public EndpointSelectionResult selectCurrent(String question, Integer maxCandidates) {
        return select(agentContextStore.currentRepoId(), question, maxCandidates);
    }

    public EndpointSelectionResult select(String repoId, String question, Integer maxCandidates) {
        QueryUnderstandingResult query = queryUnderstandingService.understand(question);
        int limit = normalizeMaxCandidates(maxCandidates);
        log.info("Endpoint selector started: repoId={}, keywordCount={}, maxCandidates={}",
                repoId,
                query.keywords().size(),
                limit
        );

        List<EndpointCandidateResult> scored = endpointLookupService.listEndpoints(repoId).stream()
                .map(endpoint -> scoreEndpoint(endpoint, query.keywords()))
                .sorted(Comparator.comparingInt(EndpointCandidateResult::score).reversed())
                .toList();

        List<EndpointCandidateResult> candidates = selectCandidates(scored, limit);
        log.info("Endpoint selector finished: repoId={}, selectedCount={}", repoId, candidates.size());
        return new EndpointSelectionResult(repoId, query.rawQuestion(), query, candidates);
    }

    private EndpointCandidateResult scoreEndpoint(EndpointLookupResult endpoint, List<String> keywords) {
        if (keywords.isEmpty()) {
            return new EndpointCandidateResult(endpoint, 0, "No keywords were extracted; fallback candidate.");
        }

        String searchable = searchableEndpointText(endpoint);
        int score = 0;
        List<String> matched = new ArrayList<>();
        for (String keyword : keywords) {
            String normalizedKeyword = keyword.toLowerCase(Locale.ROOT);
            if (searchable.contains(normalizedKeyword)) {
                score += keywordWeight(normalizedKeyword);
                matched.add(keyword);
            }
        }

        String reason = matched.isEmpty()
                ? "No keyword matched; fallback candidate."
                : "Matched keywords: " + String.join(", ", matched);
        return new EndpointCandidateResult(endpoint, score, reason);
    }

    private String searchableEndpointText(EndpointLookupResult endpoint) {
        return splitCamelCase(String.join(" ",
                value(endpoint.path()),
                value(endpoint.path()).replace("/", " ").replace("{", " ").replace("}", " "),
                value(endpoint.controllerClass()),
                value(endpoint.handlerMethod()),
                value(endpoint.httpMethod())
        )).replace('-', ' ')
                .replace('_', ' ')
                .toLowerCase(Locale.ROOT);
    }

    private int keywordWeight(String keyword) {
        if (ERROR_SIGNAL_WORDS.contains(keyword)) {
            return 2;
        }
        return Math.max(1, Math.min(keyword.length(), 8));
    }

    private List<EndpointCandidateResult> selectCandidates(
            List<EndpointCandidateResult> scoredEndpoints,
            int maxCandidates
    ) {
        List<EndpointCandidateResult> positiveMatches = scoredEndpoints.stream()
                .filter(candidate -> candidate.score() > 0)
                .limit(maxCandidates)
                .toList();
        if (!positiveMatches.isEmpty()) {
            return positiveMatches;
        }
        return scoredEndpoints.stream()
                .limit(maxCandidates)
                .toList();
    }

    private int normalizeMaxCandidates(Integer maxCandidates) {
        if (maxCandidates == null || maxCandidates <= 0) {
            return DEFAULT_MAX_CANDIDATES;
        }
        return Math.min(maxCandidates, 10);
    }

    private String splitCamelCase(String value) {
        return value.replaceAll("(?<=[a-z0-9])(?=[A-Z])", " ");
    }

    private String value(String value) {
        return value == null ? "" : value;
    }
}
