package com.legacypilot.service;

import com.legacypilot.entity.AnalysisTask;
import org.springframework.stereotype.Service;

@Service
public class AnalysisService {

    public AnalysisTask getStatus() {
        return new AnalysisTask(null, "ready");
    }
}
