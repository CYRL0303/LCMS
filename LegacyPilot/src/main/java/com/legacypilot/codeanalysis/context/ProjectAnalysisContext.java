package com.legacypilot.codeanalysis.context;

import com.legacypilot.codeanalysis.detector.ProjectType;
import java.nio.file.Path;
import java.util.List;

/**
 * Immutable input passed to every code parser for a repository analysis run.
 */
public record ProjectAnalysisContext(
        String repoId,
        Path repositoryRoot,
        ProjectType projectType,
        List<SourceFile> sourceFiles
) {
    public List<SourceFile> javaFiles() {
        return sourceFiles.stream()
                .filter(file -> file.type() == SourceFileType.JAVA)
                .toList();
    }

    public List<SourceFile> xmlFiles() {
        return sourceFiles.stream()
                .filter(file -> file.type() == SourceFileType.XML)
                .toList();
    }
}
