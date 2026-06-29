package com.legacypilot.codeanalysis.context;

import java.nio.file.Path;

/**
 * Source file metadata shared by code analysis parsers.
 */
public record SourceFile(
        Path absolutePath,
        String relativePath,
        SourceFileType type
) {
}
