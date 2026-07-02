package com.legacypilot.agenttool.evidence.service;

import com.legacypilot.agenttool.evidence.dto.EndpointEvidenceResult;
import com.legacypilot.agenttool.evidence.dto.EvidenceItemResult;
import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import com.legacypilot.codeanalysis.service.CodeAnalysisResultStore;
import com.legacypilot.repository.entity.RepositoryIndex;
import com.legacypilot.repository.service.RepositoryService;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Agent tool for retrieving source evidence linked to code-analysis facts.
 */
@Service
public class EvidenceLookupService {
    private static final Logger log = LoggerFactory.getLogger(EvidenceLookupService.class);
    private static final int SNIPPET_RADIUS = 6;

    private final CodeAnalysisResultStore codeAnalysisResultStore;
    private final RepositoryService repositoryService;

    public EvidenceLookupService(
            CodeAnalysisResultStore codeAnalysisResultStore,
            RepositoryService repositoryService
    ) {
        this.codeAnalysisResultStore = codeAnalysisResultStore;
        this.repositoryService = repositoryService;
    }

    public EndpointEvidenceResult getEndpointEvidence(String repoId, String endpointId) {
        if (endpointId == null || endpointId.isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "endpointId is required.");
        }

        CodeAnalysisResult result = codeAnalysisResultStore.get(repoId);
        RepositoryIndex repository = repositoryService.getRepository(repoId);
        CodeEndpoint endpoint = result.endpoints().stream()
                .filter(candidate -> endpointId.equals(candidate.endpointId()))
                .findFirst()
                .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Endpoint not found: " + endpointId));

        log.info("Agent工具读取接口证据：repoId={}，endpointId={}，evidenceCount={}",
                repoId,
                endpointId,
                endpoint.evidenceRefs().size()
        );

        List<EvidenceItemResult> items = endpoint.evidenceRefs().stream()
                .map(evidence -> toEvidenceItem(repository, evidence))
                .toList();

        return new EndpointEvidenceResult(
                repoId,
                endpoint.endpointId(),
                endpoint.httpMethod(),
                endpoint.path(),
                endpoint.controllerClass(),
                endpoint.handlerMethod(),
                items
        );
    }

    private EvidenceItemResult toEvidenceItem(RepositoryIndex repository, EvidenceRef evidence) {
        SourceSnippet snippet = readSnippet(repository, evidence);
        return new EvidenceItemResult(
                evidence.evidenceId(),
                evidence.filePath(),
                evidence.startLine(),
                evidence.endLine(),
                evidence.extractionMethod(),
                evidence.confidence(),
                snippet.startLine(),
                snippet.endLine(),
                snippet.text()
        );
    }

    private SourceSnippet readSnippet(RepositoryIndex repository, EvidenceRef evidence) {
        if (repository.localRepoPath() == null || repository.localRepoPath().isBlank()) {
            log.warn("Agent工具无法读取证据源码：repoId={} 没有本地路径", repository.repoId());
            return fallbackSnippet(evidence);
        }
        if (evidence.filePath() == null || evidence.filePath().isBlank()) {
            log.warn("Agent工具无法读取证据源码：evidenceId={} 没有文件路径", evidence.evidenceId());
            return fallbackSnippet(evidence);
        }

        Path repoRoot = Path.of(repository.localRepoPath()).toAbsolutePath().normalize();
        Path evidencePath = repoRoot.resolve(evidence.filePath()).normalize();
        if (!evidencePath.startsWith(repoRoot)) {
            log.warn("Agent工具拒绝读取仓库外证据文件：repoId={}，filePath={}", repository.repoId(), evidence.filePath());
            return fallbackSnippet(evidence);
        }

        try {
            List<String> lines = Files.readAllLines(evidencePath, StandardCharsets.UTF_8);
            int anchorLine = safeLine(evidence.startLine(), evidence.endLine());
            int startLine = Math.max(1, anchorLine - SNIPPET_RADIUS);
            int endLine = Math.min(lines.size(), anchorLine + SNIPPET_RADIUS);
            String codeSnippet = String.join(System.lineSeparator(), lines.subList(startLine - 1, endLine));
            return new SourceSnippet(startLine, endLine, codeSnippet);
        } catch (IOException | RuntimeException ex) {
            log.warn("Agent工具读取证据源码失败：repoId={}，filePath={}，reason={}",
                    repository.repoId(),
                    evidence.filePath(),
                    ex.getMessage()
            );
            return fallbackSnippet(evidence);
        }
    }

    private SourceSnippet fallbackSnippet(EvidenceRef evidence) {
        return new SourceSnippet(evidence.startLine(), evidence.endLine(), evidence.excerpt());
    }

    private int safeLine(Integer startLine, Integer endLine) {
        if (startLine != null && startLine > 0) {
            return startLine;
        }
        if (endLine != null && endLine > 0) {
            return endLine;
        }
        return 1;
    }

    private record SourceSnippet(
            Integer startLine,
            Integer endLine,
            String text
    ) {
    }
}
