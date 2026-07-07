package com.legacypilot.codeanalysis.parser;

import com.legacypilot.codeanalysis.context.ProjectAnalysisContext;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import com.legacypilot.codeanalysis.parser.java.JavaClassInfo;
import com.legacypilot.codeanalysis.parser.java.JavaClassKind;
import com.legacypilot.codeanalysis.parser.java.JavaMethodInfo;
import com.legacypilot.codeanalysis.parser.java.JavaProjectModel;
import com.legacypilot.codeanalysis.parser.java.JavaSourceAnalyzer;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * Builds the base code structure graph from the shared JavaProjectModel.
 */
@Component
public class JavaSourceStructureParser implements CodeParser {
    private final JavaSourceAnalyzer javaSourceAnalyzer;

    public JavaSourceStructureParser(JavaSourceAnalyzer javaSourceAnalyzer) {
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
            addClass(context, result, classInfo);
            for (JavaMethodInfo method : classInfo.methods()) {
                addMethod(context, result, classInfo, method);
            }
        }
        return result.build();
    }

    private void addClass(ProjectAnalysisContext context, CodeParseResult.Builder result, JavaClassInfo classInfo) {
        EvidenceRef evidence = evidence(
                context.repoId(),
                classInfo.sourceFile().relativePath(),
                classInfo.line(),
                classInfo.simpleName(),
                "java_structure_class",
                0.82
        );
        result.addEvidence(evidence);
        result.addNode(new CodeNode(
                classNodeId(context.repoId(), classInfo),
                classNodeType(classInfo.kind()),
                classInfo.simpleName(),
                classInfo.qualifiedName(),
                List.of(evidence)
        ));
        result.incrementClassCount();
    }

    private void addMethod(
            ProjectAnalysisContext context,
            CodeParseResult.Builder result,
            JavaClassInfo classInfo,
            JavaMethodInfo method
    ) {
        EvidenceRef evidence = evidence(
                context.repoId(),
                classInfo.sourceFile().relativePath(),
                method.startLine(),
                method.signature(),
                "java_structure_method",
                0.8
        );
        result.addEvidence(evidence);
        result.addNode(new CodeNode(
                methodNodeId(context.repoId(), classInfo, method.name()),
                methodNodeType(classInfo.kind()),
                method.name(),
                classInfo.qualifiedName() + "." + method.name(),
                List.of(evidence)
        ));
        result.addEdge(new CodeEdge(
                edgeId(context.repoId(), "DECLARES", classNodeId(context.repoId(), classInfo), methodNodeId(context.repoId(), classInfo, method.name())),
                classNodeId(context.repoId(), classInfo),
                methodNodeId(context.repoId(), classInfo, method.name()),
                "DECLARES",
                0.82,
                List.of(evidence)
        ));
        result.incrementMethodCount();
    }

    private String classNodeType(JavaClassKind kind) {
        return switch (kind) {
            case CONTROLLER -> "Controller Class";
            case SERVICE -> "Service Class";
            case REPOSITORY -> "Repository Class";
            case MAPPER -> "Mapper Class";
            case CONFIGURATION -> "Configuration Class";
            case COMPONENT -> "Component Class";
            default -> "Class";
        };
    }

    private String methodNodeType(JavaClassKind kind) {
        return switch (kind) {
            case CONTROLLER -> "Handler Method";
            case SERVICE -> "Service Method";
            case REPOSITORY -> "Repository Method";
            case MAPPER -> "Mapper Method";
            default -> "Method";
        };
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
}
