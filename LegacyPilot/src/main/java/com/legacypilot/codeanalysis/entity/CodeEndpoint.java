package com.legacypilot.codeanalysis.entity;

import java.util.List;

/**
 * Spring-style HTTP endpoint fact used by the frontend endpoint analysis page.
 */
public record CodeEndpoint(
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
