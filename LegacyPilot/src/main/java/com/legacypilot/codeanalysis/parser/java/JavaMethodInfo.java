package com.legacypilot.codeanalysis.parser.java;

import java.util.List;

public record JavaMethodInfo(
        String name,
        String signature,
        int parameterCount,
        List<String> parameterTypes,
        int startLine,
        int endLine,
        String body,
        List<JavaMethodCallInfo> calls
) {
}
