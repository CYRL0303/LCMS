package com.legacypilot.codeanalysis.parser.java;

public record JavaMethodCallInfo(
        String receiverName,
        String methodName,
        int argumentCount,
        int line,
        String evidence
) {
}
