package com.legacypilot.agenttool.trace.service;

import com.legacypilot.agenttool.trace.dto.EndpointTraceRequest;
import com.legacypilot.agenttool.trace.dto.EndpointTraceToolResult;
import com.legacypilot.codeanalysis.dto.EndpointTraceResult;
import com.legacypilot.codeanalysis.service.EndpointTraceService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Agent tool boundary for endpoint trace queries.
 */
@Service
public class EndpointTraceToolService {
    private static final Logger log = LoggerFactory.getLogger(EndpointTraceToolService.class);

    private final EndpointTraceService endpointTraceService;

    public EndpointTraceToolService(EndpointTraceService endpointTraceService) {
        this.endpointTraceService = endpointTraceService;
    }

    public EndpointTraceToolResult traceEndpoint(String repoId, EndpointTraceRequest request) {
        EndpointTraceResult trace = endpointTraceService.traceEndpoint(
                repoId,
                request.endpointId(),
                request.httpMethod(),
                request.path(),
                request.maxDepth()
        );
        log.info("Agent工具追踪接口调用链：repoId={}，endpointId={}，paths={}，nodes={}，edges={}",
                repoId,
                trace.endpoint().endpointId(),
                trace.graphPaths().size(),
                trace.matchedNodes().size(),
                trace.matchedEdges().size()
        );
        return new EndpointTraceToolResult(
                trace.repoId(),
                trace.endpoint(),
                trace.graphPaths(),
                trace.matchedNodes(),
                trace.matchedEdges(),
                trace.evidenceRefs()
        );
    }
}
