package com.legacypilot.codeanalysis.entity;

import java.util.List;

/**
 * Normalized graph node produced by parser modules.
 */
public record CodeNode(
        String nodeId,
        String type,
        String name,
        String qualifiedName,
        List<EvidenceRef> evidenceRefs
) {
}
