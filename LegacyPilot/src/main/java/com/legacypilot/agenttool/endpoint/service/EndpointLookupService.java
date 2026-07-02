package com.legacypilot.agenttool.endpoint.service;

import com.legacypilot.agenttool.endpoint.dto.EndpointLookupResult;
import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.service.CodeAnalysisResultStore;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Agent tool for exposing endpoint context from the current code-analysis graph.
 */
@Service
public class EndpointLookupService {
    private static final Logger log = LoggerFactory.getLogger(EndpointLookupService.class);

    private final CodeAnalysisResultStore codeAnalysisResultStore;

    public EndpointLookupService(CodeAnalysisResultStore codeAnalysisResultStore) {
        this.codeAnalysisResultStore = codeAnalysisResultStore;
    }

    public List<EndpointLookupResult> listEndpoints(String repoId) {
        CodeAnalysisResult result = codeAnalysisResultStore.get(repoId);
        log.info("Agent工具读取当前项目接口上下文：repoId={}，endpointCount={}", repoId, result.endpoints().size());
        return result.endpoints().stream()
                .map(endpoint -> toLookupResult(repoId, endpoint))
                .toList();
    }

    public EndpointLookupResult findEndpoint(String repoId, String path) {
        CodeAnalysisResult result = codeAnalysisResultStore.get(repoId);
        String normalizedPath = normalizeEndpointPath(path);
        return result.endpoints().stream()
                .filter(endpoint -> endpoint.path().equals(normalizedPath))
                .findFirst()
                .map(endpoint -> toLookupResult(repoId, endpoint))
                .orElseThrow(() -> {
                    log.warn("Agent工具未找到接口：repoId={}，path={}", repoId, normalizedPath);
                    return new ResponseStatusException(NOT_FOUND, "Endpoint not found in code analysis result.");
                });
    }

    private EndpointLookupResult toLookupResult(String repoId, CodeEndpoint endpoint) {
        log.info("Agent工具读取接口：repoId={}，path={}，handler={}.{}",
                repoId,
                endpoint.path(),
                endpoint.controllerClass(),
                endpoint.handlerMethod()
        );
        return new EndpointLookupResult(
                repoId,
                endpoint.endpointId(),
                endpoint.httpMethod(),
                endpoint.path(),
                endpoint.controllerClass(),
                endpoint.handlerMethod(),
                endpoint.filePath(),
                endpoint.lineNumber(),
                endpoint.evidenceRefs()
        );
    }

    private String normalizeEndpointPath(String path) {
        if (path == null || path.isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "Endpoint path is required.");
        }
        String normalized = path.trim().replace('\\', '/');
        normalized = normalized.replaceAll("/{2,}", "/");
        if (!normalized.startsWith("/")) {
            normalized = "/" + normalized;
        }
        if (normalized.length() > 1) {
            normalized = normalized.replaceAll("/+$", "");
        }
        return normalized;
    }
}
