package com.legacypilot.codeanalysis.dto;

import java.util.List;

public record CodeTracePath(
        List<String> nodeIds,
        List<String> edgeIds
) {
}
