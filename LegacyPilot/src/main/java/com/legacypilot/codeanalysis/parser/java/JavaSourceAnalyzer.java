package com.legacypilot.codeanalysis.parser.java;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.MethodReferenceExpr;
import com.github.javaparser.ast.nodeTypes.NodeWithAnnotations;
import com.legacypilot.codeanalysis.context.ProjectAnalysisContext;
import com.legacypilot.codeanalysis.context.SourceFile;
import java.io.IOException;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Shared Java source analyzer backed by JavaParser AST.
 *
 * The graph builders depend on JavaProjectModel, not on JavaParser directly.
 * This keeps AST parsing replaceable while improving extraction quality over
 * the earlier regex implementation.
 */
@Component
public class JavaSourceAnalyzer {
    private static final Logger log = LoggerFactory.getLogger(JavaSourceAnalyzer.class);

    public JavaProjectModel analyze(ProjectAnalysisContext context) {
        Map<String, JavaClassInfo> classesBySimpleName = new LinkedHashMap<>();
        Map<String, JavaClassInfo> classesByQualifiedName = new LinkedHashMap<>();
        for (SourceFile file : context.javaFiles()) {
            parseClasses(file).forEach(classInfo -> {
                classesBySimpleName.put(classInfo.simpleName(), classInfo);
                classesByQualifiedName.put(classInfo.qualifiedName(), classInfo);
            });
        }
        return new JavaProjectModel(
                List.copyOf(classesByQualifiedName.values()),
                Map.copyOf(classesBySimpleName),
                Map.copyOf(classesByQualifiedName)
        );
    }

    private List<JavaClassInfo> parseClasses(SourceFile file) {
        try {
            CompilationUnit compilationUnit = StaticJavaParser.parse(file.absolutePath());
            String packageName = compilationUnit.getPackageDeclaration()
                    .map(packageDeclaration -> packageDeclaration.getNameAsString())
                    .orElse(null);
            List<String> imports = compilationUnit.getImports().stream()
                    .filter(importDeclaration -> !importDeclaration.isAsterisk())
                    .map(ImportDeclaration::getNameAsString)
                    .toList();
            List<JavaClassInfo> classes = new ArrayList<>();
            for (TypeDeclaration<?> type : compilationUnit.getTypes()) {
                if (type instanceof ClassOrInterfaceDeclaration classDeclaration) {
                    classes.add(classInfo(file, packageName, imports, classDeclaration));
                } else if (type instanceof EnumDeclaration enumDeclaration) {
                    classes.add(classInfo(file, packageName, imports, enumDeclaration));
                }
            }
            return List.copyOf(classes);
        } catch (IOException exception) {
            log.warn("Java AST analysis skipped file: file={}, reason={}", file.relativePath(), exception.getMessage());
            return List.of();
        } catch (RuntimeException exception) {
            log.warn("Java AST parse failed: file={}, reason={}", file.relativePath(), exception.getMessage());
            return List.of();
        }
    }

    private JavaClassInfo classInfo(
            SourceFile file,
            String packageName,
            List<String> imports,
            TypeDeclaration<?> type
    ) {
        String simpleName = type.getNameAsString();
        String qualifiedName = packageName == null ? simpleName : packageName + "." + simpleName;
        return new JavaClassInfo(
                file,
                packageName,
                imports,
                simpleName,
                qualifiedName,
                line(type).orElse(1),
                classifyClass(simpleName, type),
                dependencies(type, simpleName, imports, packageName),
                methods(type)
        );
    }

    private Map<String, JavaDependencyInfo> dependencies(
            TypeDeclaration<?> type,
            String className,
            List<String> imports,
            String packageName
    ) {
        Map<String, JavaDependencyInfo> dependencies = new LinkedHashMap<>();
        for (FieldDeclaration field : type.getFields()) {
            String typeName = simpleTypeName(field.getElementType().asString());
            for (var variable : field.getVariables()) {
                String variableName = variable.getNameAsString();
                dependencies.put(variableName, new JavaDependencyInfo(
                        variableName,
                        typeName,
                        qualifiedTypeName(typeName, imports, packageName),
                        line(field).orElse(1),
                        field.toString().replaceAll("\\s+", " ").trim()
                ));
            }
        }

        for (ConstructorDeclaration constructor : type.findAll(ConstructorDeclaration.class)) {
            if (!constructor.getNameAsString().equals(className)) {
                continue;
            }
            for (Parameter parameter : constructor.getParameters()) {
                String typeName = simpleTypeName(parameter.getType().asString());
                String variableName = parameter.getNameAsString();
                dependencies.putIfAbsent(variableName, new JavaDependencyInfo(
                        variableName,
                        typeName,
                        qualifiedTypeName(typeName, imports, packageName),
                        line(constructor).orElse(1),
                        parameter.toString().replaceAll("\\s+", " ").trim()
                ));
            }
        }

        for (MethodDeclaration method : type.getMethods()) {
            List<String> annotations = annotationNames(method);
            if (!hasAnnotation(annotations, "Autowired") || !method.getNameAsString().startsWith("set")) {
                continue;
            }
            for (Parameter parameter : method.getParameters()) {
                String typeName = simpleTypeName(parameter.getType().asString());
                String variableName = setterDependencyName(method.getNameAsString(), parameter.getNameAsString());
                dependencies.putIfAbsent(variableName, new JavaDependencyInfo(
                        variableName,
                        typeName,
                        qualifiedTypeName(typeName, imports, packageName),
                        line(method).orElse(1),
                        method.getDeclarationAsString(false, false, false)
                ));
            }
        }
        return Map.copyOf(dependencies);
    }

    private List<JavaMethodInfo> methods(TypeDeclaration<?> type) {
        List<JavaMethodInfo> methods = new ArrayList<>();
        for (MethodDeclaration method : type.getMethods()) {
            methods.add(new JavaMethodInfo(
                    method.getNameAsString(),
                    method.getDeclarationAsString(false, false, false),
                    method.getParameters().size(),
                    method.getParameters().stream()
                            .map(parameter -> simpleTypeName(parameter.getType().asString()))
                            .toList(),
                    line(method).orElse(1),
                    method.getEnd().map(position -> position.line).orElse(line(method).orElse(1)),
                    method.getBody().map(Node::toString).orElse(""),
                    calls(method)
            ));
        }
        return List.copyOf(methods);
    }

    private List<JavaMethodCallInfo> calls(MethodDeclaration method) {
        List<JavaMethodCallInfo> calls = new ArrayList<>();
        method.findAll(MethodCallExpr.class).stream()
                .map(call -> new JavaMethodCallInfo(
                        receiverName(call),
                        call.getNameAsString(),
                        call.getArguments().size(),
                        line(call).orElse(line(method).orElse(1)),
                        call.toString().replaceAll("\\s+", " ").trim()
                ))
                .forEach(calls::add);
        method.findAll(MethodReferenceExpr.class).stream()
                .map(reference -> new JavaMethodCallInfo(
                        receiverName(reference.getScope()),
                        reference.getIdentifier(),
                        -1,
                        line(reference).orElse(line(method).orElse(1)),
                        reference.toString().replaceAll("\\s+", " ").trim()
                ))
                .forEach(calls::add);
        return List.copyOf(calls);
    }

    private String receiverName(MethodCallExpr call) {
        Optional<Expression> scope = call.getScope();
        if (scope.isEmpty()) {
            return null;
        }
        return receiverName(scope.get());
    }

    private String receiverName(Expression expression) {
        if (expression.isNameExpr()) {
            return expression.asNameExpr().getNameAsString();
        }
        if (expression.isFieldAccessExpr()) {
            return expression.asFieldAccessExpr().getNameAsString();
        }
        if (expression.isThisExpr()) {
            return "this";
        }
        if (expression.isSuperExpr()) {
            return "super";
        }
        if (expression.isMethodCallExpr()) {
            MethodCallExpr nestedCall = expression.asMethodCallExpr();
            return nestedCall.getScope()
                    .map(this::receiverName)
                    .orElse(nestedCall.toString());
        }
        return expression.toString();
    }

    private String setterDependencyName(String methodName, String parameterName) {
        if (methodName.length() <= 3) {
            return parameterName;
        }
        String propertyName = methodName.substring(3);
        return Character.toLowerCase(propertyName.charAt(0)) + propertyName.substring(1);
    }

    private JavaClassKind classifyClass(String className, TypeDeclaration<?> type) {
        List<String> annotations = annotationNames(type);
        if (hasAnnotation(annotations, "RestController", "Controller") || className.endsWith("Controller")) {
            return JavaClassKind.CONTROLLER;
        }
        if (hasAnnotation(annotations, "Service") || className.endsWith("Service")) {
            return JavaClassKind.SERVICE;
        }
        if (hasAnnotation(annotations, "Mapper") || className.endsWith("Mapper")) {
            return JavaClassKind.MAPPER;
        }
        if (hasAnnotation(annotations, "Repository") || className.endsWith("Repository")) {
            return JavaClassKind.REPOSITORY;
        }
        if (hasAnnotation(annotations, "Configuration") || className.endsWith("Config") || className.endsWith("Configuration")) {
            return JavaClassKind.CONFIGURATION;
        }
        if (hasAnnotation(annotations, "Component")) {
            return JavaClassKind.COMPONENT;
        }
        return JavaClassKind.OTHER;
    }

    private List<String> annotationNames(NodeWithAnnotations<?> node) {
        return node.getAnnotations().stream()
                .map(AnnotationExpr::getNameAsString)
                .map(this::simpleTypeName)
                .toList();
    }

    private boolean hasAnnotation(List<String> annotations, String... expectedNames) {
        for (String expectedName : expectedNames) {
            if (annotations.contains(expectedName)) {
                return true;
            }
        }
        return false;
    }

    private String qualifiedTypeName(String simpleName, List<String> imports, String packageName) {
        for (String importName : imports) {
            if (importName.endsWith("." + simpleName)) {
                return importName;
            }
        }
        return packageName == null ? simpleName : packageName + "." + simpleName;
    }

    private String simpleTypeName(String typeName) {
        String cleaned = typeName == null ? "" : typeName.trim();
        int genericStart = cleaned.indexOf('<');
        if (genericStart >= 0) {
            cleaned = cleaned.substring(0, genericStart);
        }
        int arrayStart = cleaned.indexOf('[');
        if (arrayStart >= 0) {
            cleaned = cleaned.substring(0, arrayStart);
        }
        int dot = cleaned.lastIndexOf('.');
        return dot >= 0 ? cleaned.substring(dot + 1) : cleaned;
    }

    private Optional<Integer> line(Node node) {
        return node.getBegin().map(position -> position.line);
    }
}
