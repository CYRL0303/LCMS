package com.legacypilot.agenttool.graph.service;

import com.legacypilot.agenttool.graph.dto.CodeGraphResult;
import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.service.CodeAnalysisResultStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Agent tool for reading the current code graph produced by codeanalysis.
 */
@Service
public class CodeGraphService {
    private static final Logger log = LoggerFactory.getLogger(CodeGraphService.class);

    private final CodeAnalysisResultStore codeAnalysisResultStore;

    public CodeGraphService(CodeAnalysisResultStore codeAnalysisResultStore) {
        this.codeAnalysisResultStore = codeAnalysisResultStore;
    }

    public CodeGraphResult getGraph(String repoId) {
        CodeAnalysisResult result = codeAnalysisResultStore.get(repoId);
        log.info("Agent工具读取代码图谱：repoId={}，nodeCount={}，edgeCount={}，endpointCount={}",
                repoId,
                result.summary().nodeCount(),
                result.summary().edgeCount(),
                result.summary().endpointCount()
        );
        return CodeGraphResult.from(result);
    }
}
