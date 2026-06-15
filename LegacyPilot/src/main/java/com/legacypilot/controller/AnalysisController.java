package com.legacypilot.controller;

import com.legacypilot.entity.AnalysisTask;
import com.legacypilot.service.AnalysisService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/analysis")
public class AnalysisController {

    private final AnalysisService analysisService;

    public AnalysisController(AnalysisService analysisService) {
        this.analysisService = analysisService;
    }

    @GetMapping("/status")
    public AnalysisTask getStatus() {
        return analysisService.getStatus();
    }
}
