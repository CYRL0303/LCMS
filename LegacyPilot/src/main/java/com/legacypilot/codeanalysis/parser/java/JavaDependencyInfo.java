package com.legacypilot.codeanalysis.parser.java;

public record JavaDependencyInfo(
        String variableName,
        String typeName,
        String qualifiedTypeName,
        int line,
        String evidence
) {
}
