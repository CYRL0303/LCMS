package com.legacypilot.agenttool.query.controller;

import com.legacypilot.agenttool.query.dto.QueryUnderstandingRequest;
import com.legacypilot.agenttool.query.dto.QueryUnderstandingResult;
import com.legacypilot.agenttool.query.service.QueryUnderstandingService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Query-understanding HTTP entry point for agent-tool debugging.
 */
@RestController
@RequestMapping("/api/agent/tools/query")
public class QueryUnderstandingToolController {
    private final QueryUnderstandingService queryUnderstandingService;

    public QueryUnderstandingToolController(QueryUnderstandingService queryUnderstandingService) {
        this.queryUnderstandingService = queryUnderstandingService;
    }

    @PostMapping("/understand")
    public QueryUnderstandingResult understand(@RequestBody QueryUnderstandingRequest request) {
        return queryUnderstandingService.understand(request.question());
    }
}
