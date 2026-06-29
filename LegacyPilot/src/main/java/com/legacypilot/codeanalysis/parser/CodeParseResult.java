package com.legacypilot.codeanalysis.parser;

import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.util.ArrayList;
import java.util.List;

/**
 * Parser contribution merged by JavaCodeAnalysisService.
 */
public record CodeParseResult(
        List<CodeNode> nodes,
        List<CodeEdge> edges,
        List<CodeEndpoint> endpoints,
        List<EvidenceRef> evidenceRefs,
        int classCount,
        int methodCount
) {
    public static CodeParseResult empty() {
        return new CodeParseResult(List.of(), List.of(), List.of(), List.of(), 0, 0);
    }

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private final List<CodeNode> nodes = new ArrayList<>();
        private final List<CodeEdge> edges = new ArrayList<>();
        private final List<CodeEndpoint> endpoints = new ArrayList<>();
        private final List<EvidenceRef> evidenceRefs = new ArrayList<>();
        private int classCount;
        private int methodCount;

        public Builder addNode(CodeNode node) {
            nodes.add(node);
            return this;
        }

        public Builder addEdge(CodeEdge edge) {
            edges.add(edge);
            return this;
        }

        public Builder addEndpoint(CodeEndpoint endpoint) {
            endpoints.add(endpoint);
            return this;
        }

        public Builder addEvidence(EvidenceRef evidenceRef) {
            evidenceRefs.add(evidenceRef);
            return this;
        }

        public Builder incrementClassCount() {
            classCount++;
            return this;
        }

        public Builder incrementMethodCount() {
            methodCount++;
            return this;
        }

        public CodeParseResult build() {
            return new CodeParseResult(
                    List.copyOf(nodes),
                    List.copyOf(edges),
                    List.copyOf(endpoints),
                    List.copyOf(evidenceRefs),
                    classCount,
                    methodCount
            );
        }
    }
}
