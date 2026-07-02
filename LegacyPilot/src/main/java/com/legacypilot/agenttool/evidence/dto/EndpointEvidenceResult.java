package com.legacypilot.agenttool.evidence.dto;

import java.util.List;

/**
 * Response DTO containing evidence items for one endpoint.
 */
public record EndpointEvidenceResult(
        String repoId,
        String endpointId,
        String httpMethod,
        String path,
        String controllerClass,
        String handlerMethod,
        List<EvidenceItemResult> items
) {
}
