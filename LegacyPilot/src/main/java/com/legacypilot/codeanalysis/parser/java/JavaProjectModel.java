package com.legacypilot.codeanalysis.parser.java;

import java.util.List;
import java.util.Map;

public record JavaProjectModel(
        List<JavaClassInfo> classes,
        Map<String, JavaClassInfo> classesBySimpleName,
        Map<String, JavaClassInfo> classesByQualifiedName
) {
    public JavaClassInfo resolveClass(String typeName, JavaClassInfo currentClass) {
        if (typeName == null || typeName.isBlank()) {
            return null;
        }
        String simpleName = simpleTypeName(typeName);
        JavaClassInfo simpleMatch = classesBySimpleName.get(simpleName);
        if (simpleMatch != null) {
            return simpleMatch;
        }
        for (String importName : currentClass.imports()) {
            if (importName.endsWith("." + simpleName)) {
                return classesByQualifiedName.get(importName);
            }
        }
        String samePackageName = currentClass.packageName() == null
                ? simpleName
                : currentClass.packageName() + "." + simpleName;
        return classesByQualifiedName.get(samePackageName);
    }

    private String simpleTypeName(String typeName) {
        String cleaned = typeName.trim();
        int genericStart = cleaned.indexOf('<');
        if (genericStart >= 0) {
            cleaned = cleaned.substring(0, genericStart);
        }
        int dot = cleaned.lastIndexOf('.');
        return dot >= 0 ? cleaned.substring(dot + 1) : cleaned;
    }
}
