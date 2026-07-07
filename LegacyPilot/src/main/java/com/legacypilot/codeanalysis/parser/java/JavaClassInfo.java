package com.legacypilot.codeanalysis.parser.java;

import com.legacypilot.codeanalysis.context.SourceFile;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public record JavaClassInfo(
        SourceFile sourceFile,
        String packageName,
        List<String> imports,
        String simpleName,
        String qualifiedName,
        int line,
        JavaClassKind kind,
        Map<String, JavaDependencyInfo> dependenciesByVariable,
        List<JavaMethodInfo> methods
) {
    public boolean hasMethod(String methodName) {
        return methods.stream().anyMatch(method -> method.name().equals(methodName));
    }

    public Optional<JavaMethodInfo> findMethod(String methodName) {
        return methods.stream()
                .filter(method -> method.name().equals(methodName))
                .findFirst();
    }

    public Optional<JavaMethodInfo> findMethod(String methodName, int argumentCount) {
        if (argumentCount < 0) {
            return findMethod(methodName);
        }
        Optional<JavaMethodInfo> exactArityMatch = methods.stream()
                .filter(method -> method.name().equals(methodName))
                .filter(method -> method.parameterCount() == argumentCount)
                .findFirst();
        return exactArityMatch.or(() -> findMethod(methodName));
    }
}
