package com.legacypilot.agenttool.endpointselector.controller;

import com.legacypilot.agenttool.endpointselector.dto.EndpointSelectionRequest;
import com.legacypilot.agenttool.endpointselector.dto.EndpointSelectionResult;
import com.legacypilot.agenttool.endpointselector.service.EndpointSelectorService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Debug controller for the endpoint selector tool.
 */
@RestController
@RequestMapping("/api/agent/tools/endpoint-selector")
public class EndpointSelectorToolController {
    private final EndpointSelectorService endpointSelectorService;

    public EndpointSelectorToolController(EndpointSelectorService endpointSelectorService) {
        this.endpointSelectorService = endpointSelectorService;
    }

    @PostMapping("/select")
    public EndpointSelectionResult select(@RequestBody EndpointSelectionRequest request) {
        return endpointSelectorService.selectCurrent(request.question(), request.maxCandidates());
    }
}
