package com.legacypilot.codeanalysis.parser;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MemberValuePair;
import com.github.javaparser.ast.expr.StringLiteralExpr;
import com.legacypilot.codeanalysis.context.ProjectAnalysisContext;
import com.legacypilot.codeanalysis.context.SourceFile;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.io.IOException;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Extracts SQL statements from method-level annotations such as @Query and
 * MyBatis @Select/@Update. This is the first SQL graph loop; XML and JDBC
 * string extraction stay separate follow-up steps.
 */
@Component
public class JavaSqlAnnotationParser implements CodeParser {
    private static final Logger log = LoggerFactory.getLogger(JavaSqlAnnotationParser.class);
    private static final Set<String> SQL_ANNOTATIONS = Set.of("Query", "Select", "Insert", "Update", "Delete");

    @Override
    public boolean supports(ProjectAnalysisContext context) {
        return !context.javaFiles().isEmpty();
    }

    @Override
    public CodeParseResult parse(ProjectAnalysisContext context) {
        CodeParseResult.Builder result = CodeParseResult.builder();
        for (SourceFile file : context.javaFiles()) {
            parseFile(context, file, result);
        }
        return result.build();
    }

    private void parseFile(ProjectAnalysisContext context, SourceFile file, CodeParseResult.Builder result) {
        try {
            CompilationUnit compilationUnit = StaticJavaParser.parse(file.absolutePath());
            for (TypeDeclaration<?> type : compilationUnit.getTypes()) {
                parseType(context, file, type, result);
            }
        } catch (IOException exception) {
            log.warn("SQL注解解析跳过文件：file={}，reason={}", file.relativePath(), exception.getMessage());
        } catch (RuntimeException exception) {
            log.warn("SQL注解解析失败：file={}，reason={}", file.relativePath(), exception.getMessage());
        }
    }

    private void parseType(
            ProjectAnalysisContext context,
            SourceFile file,
            TypeDeclaration<?> type,
            CodeParseResult.Builder result
    ) {
        for (MethodDeclaration method : type.getMethods()) {
            for (AnnotationExpr annotation : method.getAnnotations()) {
                String annotationName = simpleName(annotation.getNameAsString());
                if (!SQL_ANNOTATIONS.contains(annotationName)) {
                    continue;
                }
                extractSql(annotation).ifPresent(sql -> addSqlFact(context, file, type, method, annotationName, sql, result));
            }
        }
    }

    private Optional<String> extractSql(AnnotationExpr annotation) {
        if (annotation.isSingleMemberAnnotationExpr()) {
            return stringValue(annotation.asSingleMemberAnnotationExpr().getMemberValue());
        }
        if (annotation.isNormalAnnotationExpr()) {
            for (MemberValuePair pair : annotation.asNormalAnnotationExpr().getPairs()) {
                String name = pair.getNameAsString();
                if (name.equals("value") || name.equals("nativeQuery")) {
                    Optional<String> value = stringValue(pair.getValue());
                    if (value.isPresent()) {
                        return value;
                    }
                }
            }
        }
        return Optional.empty();
    }

    private Optional<String> stringValue(Expression expression) {
        if (expression instanceof StringLiteralExpr stringLiteral) {
            return Optional.of(normalizeSql(stringLiteral.asString()));
        }
        if (expression.isTextBlockLiteralExpr()) {
            return Optional.of(normalizeSql(expression.asTextBlockLiteralExpr().asString()));
        }
        return Optional.empty();
    }

    private void addSqlFact(
            ProjectAnalysisContext context,
            SourceFile file,
            TypeDeclaration<?> type,
            MethodDeclaration method,
            String annotationName,
            String sql,
            CodeParseResult.Builder result
    ) {
        int line = line(annotationOrMethodNode(method, annotationName)).orElse(line(method).orElse(1));
        EvidenceRef evidence = evidence(context.repoId(), file.relativePath(), line, sql, annotationName);
        String methodNodeId = methodNodeId(context.repoId(), file, method.getNameAsString());
        String sqlNodeId = sqlNodeId(context.repoId(), file, method.getNameAsString(), sql);
        result.addEvidence(evidence);
        result.addNode(new CodeNode(
                sqlNodeId,
                "SQL Statement",
                sqlName(sql),
                type.getNameAsString() + "." + method.getNameAsString() + " SQL",
                List.of(evidence)
        ));
        result.addEdge(new CodeEdge(
                edgeId(context.repoId(), "EXECUTES_SQL", methodNodeId, sqlNodeId),
                methodNodeId,
                sqlNodeId,
                "EXECUTES_SQL",
                confidence(annotationName),
                List.of(evidence)
        ));
    }

    private Node annotationOrMethodNode(MethodDeclaration method, String annotationName) {
        return method.getAnnotations().stream()
                .filter(annotation -> simpleName(annotation.getNameAsString()).equals(annotationName))
                .findFirst()
                .map(Node.class::cast)
                .orElse(method);
    }

    private Optional<Integer> line(Node node) {
        return node.getBegin().map(position -> position.line);
    }

    private EvidenceRef evidence(String repoId, String filePath, int line, String sql, String annotationName) {
        return new EvidenceRef(
                repoId + ":EV:java_sql_annotation:" + filePath + ":" + line + ":" + Math.abs(sql.hashCode()),
                filePath,
                line,
                line,
                sql,
                "java_sql_annotation_" + annotationName,
                confidence(annotationName)
        );
    }

    private String methodNodeId(String repoId, SourceFile file, String methodName) {
        return repoId + ":METHOD:" + file.relativePath() + "#" + methodName;
    }

    private String sqlNodeId(String repoId, SourceFile file, String methodName, String sql) {
        return repoId + ":SQL:" + file.relativePath() + "#" + methodName + ":" + Math.abs(sql.hashCode());
    }

    private String edgeId(String repoId, String type, String sourceNodeId, String targetNodeId) {
        return repoId + ":EDGE:" + type + ":" + sourceNodeId + "->" + targetNodeId;
    }

    private String sqlName(String sql) {
        return sql.length() <= 80 ? sql : sql.substring(0, 80) + "...";
    }

    private String normalizeSql(String sql) {
        return sql == null ? "" : sql.replaceAll("\\s+", " ").trim();
    }

    private String simpleName(String name) {
        int dot = name == null ? -1 : name.lastIndexOf('.');
        return dot >= 0 ? name.substring(dot + 1) : name;
    }

    private double confidence(String annotationName) {
        return annotationName.equals("Query") ? 0.78 : 0.84;
    }
}
