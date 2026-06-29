package com.legacypilot.codeanalysis.parser;

import com.legacypilot.codeanalysis.context.ProjectAnalysisContext;
import com.legacypilot.codeanalysis.context.SourceFile;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.io.IOException;
import java.nio.file.Files;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

/**
 * First-pass Java source structure parser.
 *
 * This parser is intentionally isolated so it can later be replaced by
 * JavaParser or Spoon without changing service orchestration.
 */
@Component
public class JavaSourceStructureParser implements CodeParser {
    private static final Pattern PACKAGE_PATTERN = Pattern.compile("\\bpackage\\s+([\\w.]+)\\s*;");
    private static final Pattern CLASS_PATTERN = Pattern.compile("\\b(class|interface|enum)\\s+(\\w+)\\b");
    private static final Pattern METHOD_PATTERN = Pattern.compile(
            "(?m)^\\s*(?:public|protected|private)\\s+(?:static\\s+)?[\\w<>\\[\\], ?]+\\s+(\\w+)\\s*\\([^;{}]*\\)\\s*(?:throws\\s+[\\w., ]+)?\\{"
    );

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
            String content = Files.readString(file.absolutePath());
            String packageName = firstGroup(PACKAGE_PATTERN, content);
            Matcher classMatcher = CLASS_PATTERN.matcher(content);
            while (classMatcher.find()) {
                String className = classMatcher.group(2);
                String qualifiedName = packageName == null ? className : packageName + "." + className;
                EvidenceRef evidence = evidence(context.repoId(), file.relativePath(), lineNumber(content, classMatcher.start()), className, "java_structure");
                result.addEvidence(evidence);
                result.addNode(new CodeNode(
                        nodeId(context.repoId(), "CLASS", qualifiedName),
                        "Class",
                        className,
                        qualifiedName,
                        List.of(evidence)
                ));
                result.incrementClassCount();
            }

            Matcher methodMatcher = METHOD_PATTERN.matcher(content);
            while (methodMatcher.find()) {
                String methodName = methodMatcher.group(1);
                EvidenceRef evidence = evidence(context.repoId(), file.relativePath(), lineNumber(content, methodMatcher.start()), methodName, "java_structure");
                result.addEvidence(evidence);
                result.addNode(new CodeNode(
                        nodeId(context.repoId(), "METHOD", file.relativePath() + "#" + methodName),
                        "Method",
                        methodName,
                        file.relativePath() + "#" + methodName,
                        List.of(evidence)
                ));
                result.incrementMethodCount();
            }
        } catch (IOException ignored) {
            // Parser failures should not prevent other parser modules from contributing.
        }
    }

    private String firstGroup(Pattern pattern, String content) {
        Matcher matcher = pattern.matcher(content);
        return matcher.find() ? matcher.group(1) : null;
    }

    private int lineNumber(String content, int offset) {
        int line = 1;
        for (int i = 0; i < offset && i < content.length(); i++) {
            if (content.charAt(i) == '\n') {
                line++;
            }
        }
        return line;
    }

    private EvidenceRef evidence(String repoId, String filePath, int line, String excerpt, String method) {
        return new EvidenceRef(
                repoId + ":EV:" + method + ":" + filePath + ":" + line,
                filePath,
                line,
                line,
                excerpt,
                method,
                0.7
        );
    }

    private String nodeId(String repoId, String type, String identity) {
        return repoId + ":" + type + ":" + identity;
    }
}
