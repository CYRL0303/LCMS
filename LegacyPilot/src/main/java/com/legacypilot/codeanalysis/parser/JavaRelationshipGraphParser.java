package com.legacypilot.codeanalysis.parser;

import com.legacypilot.codeanalysis.context.ProjectAnalysisContext;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import com.legacypilot.codeanalysis.parser.java.JavaClassInfo;
import com.legacypilot.codeanalysis.parser.java.JavaClassKind;
import com.legacypilot.codeanalysis.parser.java.JavaDependencyInfo;
import com.legacypilot.codeanalysis.parser.java.JavaMethodCallInfo;
import com.legacypilot.codeanalysis.parser.java.JavaMethodInfo;
import com.legacypilot.codeanalysis.parser.java.JavaProjectModel;
import com.legacypilot.codeanalysis.parser.java.JavaSourceAnalyzer;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Component;

/**
 * Builds cross-symbol relationship edges from the shared JavaProjectModel.
 */
@Component
public class JavaRelationshipGraphParser implements CodeParser {
    private final JavaSourceAnalyzer javaSourceAnalyzer;

    public JavaRelationshipGraphParser(JavaSourceAnalyzer javaSourceAnalyzer) {
        this.javaSourceAnalyzer = javaSourceAnalyzer;
    }

    @Override
    public boolean supports(ProjectAnalysisContext context) {
        return !context.javaFiles().isEmpty();
    }

    @Override
    public CodeParseResult parse(ProjectAnalysisContext context) {
        JavaProjectModel model = javaSourceAnalyzer.analyze(context);
        CodeParseResult.Builder result = CodeParseResult.builder();
        for (JavaClassInfo classInfo : model.classes()) {
            addDependencyEdges(context, model, result, classInfo);
            addMethodCallEdges(context, model, result, classInfo);
        }
        return result.build();
    }

    private void addDependencyEdges(
            ProjectAnalysisContext context,
            JavaProjectModel model,
            CodeParseResult.Builder result,
            JavaClassInfo sourceClass
    ) {
        Set<String> emitted = new HashSet<>();
        for (JavaDependencyInfo dependency : sourceClass.dependenciesByVariable().values()) {
            JavaClassInfo targetClass = model.resolveClass(dependency.typeName(), sourceClass);
            if (targetClass == null || targetClass.qualifiedName().equals(sourceClass.qualifiedName())) {
                continue;
            }
            String edgeType = dependencyEdgeType(sourceClass.kind(), targetClass.kind());
            if (edgeType == null || !emitted.add(edgeType + ":" + targetClass.qualifiedName())) {
                continue;
            }
            EvidenceRef evidence = evidence(
                    context.repoId(),
                    sourceClass.sourceFile().relativePath(),
                    dependency.line(),
                    dependency.evidence(),
                    "java_dependency_resolution",
                    0.74
            );
            result.addEvidence(evidence);
            result.addEdge(new CodeEdge(
                    edgeId(context.repoId(), edgeType, classNodeId(context.repoId(), sourceClass), classNodeId(context.repoId(), targetClass)),
                    classNodeId(context.repoId(), sourceClass),
                    classNodeId(context.repoId(), targetClass),
                    edgeType,
                    0.74,
                    List.of(evidence)
            ));
        }
    }

    private void addMethodCallEdges(
            ProjectAnalysisContext context,
            JavaProjectModel model,
            CodeParseResult.Builder result,
            JavaClassInfo sourceClass
    ) {
        Set<String> emitted = new HashSet<>();
        for (JavaMethodInfo sourceMethod : sourceClass.methods()) {
            for (JavaMethodCallInfo call : sourceMethod.calls()) {
                CallTarget target = targetForCall(model, sourceClass, call);
                if (target == null) {
                    continue;
                }
                JavaMethodInfo targetMethod = target.targetClass().findMethod(call.methodName(), call.argumentCount()).orElse(null);
                if (targetMethod == null) {
                    continue;
                }
                String sourceNodeId = methodNodeId(context.repoId(), sourceClass, sourceMethod.name());
                String targetNodeId = methodNodeId(context.repoId(), target.targetClass(), targetMethod.name());
                if (!emitted.add(sourceNodeId + "->" + targetNodeId)) {
                    continue;
                }
                EvidenceRef evidence = evidence(
                        context.repoId(),
                        sourceClass.sourceFile().relativePath(),
                        call.line(),
                        call.evidence(),
                        target.extractionMethod(),
                        target.confidence()
                );
                result.addEvidence(evidence);
                result.addEdge(new CodeEdge(
                        edgeId(context.repoId(), "CALLS", sourceNodeId, targetNodeId),
                        sourceNodeId,
                        targetNodeId,
                        "CALLS",
                        target.confidence(),
                        List.of(evidence)
                ));
            }
        }
    }

    private CallTarget targetForCall(JavaProjectModel model, JavaClassInfo sourceClass, JavaMethodCallInfo call) {
        if (call.receiverName() == null || call.receiverName().equals("this") || call.receiverName().equals("super")) {
            return new CallTarget(sourceClass, "java_self_method_call_resolution", 0.78);
        }
        JavaDependencyInfo dependency = sourceClass.dependenciesByVariable().get(call.receiverName());
        if (dependency != null) {
            JavaClassInfo targetClass = model.resolveClass(dependency.typeName(), sourceClass);
            if (targetClass != null) {
                return new CallTarget(targetClass, "java_dependency_method_call_resolution", 0.76);
            }
        }

        if (looksLikeTypeName(call.receiverName())) {
            JavaClassInfo staticTargetClass = model.resolveClass(call.receiverName(), sourceClass);
            if (staticTargetClass != null) {
                return new CallTarget(staticTargetClass, "java_static_method_call_resolution", 0.7);
            }
        }

        return null;
    }

    private boolean looksLikeTypeName(String value) {
        return value != null && !value.isBlank() && Character.isUpperCase(value.charAt(0));
    }

    private String dependencyEdgeType(JavaClassKind source, JavaClassKind target) {
        if (source == JavaClassKind.CONTROLLER && target == JavaClassKind.SERVICE) {
            return "USES_SERVICE";
        }
        if (source == JavaClassKind.SERVICE && (target == JavaClassKind.REPOSITORY || target == JavaClassKind.MAPPER)) {
            return "USES_REPOSITORY";
        }
        if (source == JavaClassKind.CONTROLLER && (target == JavaClassKind.REPOSITORY || target == JavaClassKind.MAPPER)) {
            return "USES_REPOSITORY";
        }
        if ((source == JavaClassKind.SERVICE || source == JavaClassKind.CONTROLLER) && target == JavaClassKind.COMPONENT) {
            return "USES_COMPONENT";
        }
        return null;
    }

    private String classNodeId(String repoId, JavaClassInfo classInfo) {
        return repoId + ":CLASS:" + classInfo.qualifiedName();
    }

    private String methodNodeId(String repoId, JavaClassInfo classInfo, String methodName) {
        return repoId + ":METHOD:" + classInfo.sourceFile().relativePath() + "#" + methodName;
    }

    private String edgeId(String repoId, String type, String sourceNodeId, String targetNodeId) {
        return repoId + ":EDGE:" + type + ":" + sourceNodeId + "->" + targetNodeId;
    }

    private EvidenceRef evidence(
            String repoId,
            String filePath,
            int line,
            String excerpt,
            String method,
            double confidence
    ) {
        return new EvidenceRef(
                repoId + ":EV:" + method + ":" + filePath + ":" + line + ":" + Math.abs(excerpt.hashCode()),
                filePath,
                line,
                line,
                excerpt,
                method,
                confidence
        );
    }

    private record CallTarget(JavaClassInfo targetClass, String extractionMethod, double confidence) {
    }
}
