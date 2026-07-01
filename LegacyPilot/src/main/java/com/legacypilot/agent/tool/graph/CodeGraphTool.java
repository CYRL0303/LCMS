package com.legacypilot.agent.tool.graph;

import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.service.CodeAnalysisResultStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Agent tool for reading the current code graph produced by codeanalysis.
 */
@Component
public class CodeGraphTool {
    private static final Logger log = LoggerFactory.getLogger(CodeGraphTool.class);

    private final CodeAnalysisResultStore codeAnalysisResultStore;

    public CodeGraphTool(CodeAnalysisResultStore codeAnalysisResultStore) {
        this.codeAnalysisResultStore = codeAnalysisResultStore;
    }

    public CodeAnalysisResult getGraph(String repoId) {
        CodeAnalysisResult result = codeAnalysisResultStore.get(repoId);
        log.info("Agent工具读取代码图谱：repoId={}，nodeCount={}，edgeCount={}，endpointCount={}",
                repoId,
                result.summary().nodeCount(),
                result.summary().edgeCount(),
                result.summary().endpointCount()
        );
        return result;
    }
}
