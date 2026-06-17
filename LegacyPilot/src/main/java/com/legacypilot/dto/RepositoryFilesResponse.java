package com.legacypilot.dto;

import java.util.List;

public record RepositoryFilesResponse(
        String repoId,
        String localRepoPath,
        int totalFiles,
        List<String> javaFiles,
        List<String> pythonFiles,
        List<String> configFiles,
        List<String> buildFiles,
        List<String> markdownFiles
) {
}