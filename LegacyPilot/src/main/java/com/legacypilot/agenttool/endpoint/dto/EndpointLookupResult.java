package com.legacypilot.agenttool.endpoint.dto;

import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.util.List;

/**
 * Response DTO returned when the endpoint lookup tool resolves an HTTP
 * endpoint to source code evidence.
 */
public record EndpointLookupResult(
        String repoId,
        String endpointId,
        String httpMethod,
        String path,
        String controllerClass,
        String handlerMethod,
        String filePath,
        Integer lineNumber,
        List<EvidenceRef> evidenceRefs
) {
}
