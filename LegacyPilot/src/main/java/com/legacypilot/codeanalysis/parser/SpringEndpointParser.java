package com.legacypilot.codeanalysis.parser;

import com.legacypilot.codeanalysis.context.ProjectAnalysisContext;
import com.legacypilot.codeanalysis.context.SourceFile;
import com.legacypilot.codeanalysis.detector.ProjectType;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import java.io.IOException;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Spring MVC endpoint parser focused on controller mapping annotations.
 */
@Component
public class SpringEndpointParser implements CodeParser {
    private static final Logger log = LoggerFactory.getLogger(SpringEndpointParser.class);

    private static final Pattern CLASS_NAME_PATTERN = Pattern.compile("\\bclass\\s+(\\w+)\\b");
    private static final Pattern CLASS_MAPPING_PATTERN = Pattern.compile("@RequestMapping\\s*\\(([^)]*)\\)");
    private static final Pattern METHOD_MAPPING_PATTERN = Pattern.compile(
            "@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\\s*(?:\\(([^)]*)\\))?"
    );
    private static final Pattern MAPPING_PATH_ATTRIBUTE_PATTERN = Pattern.compile(
            "\\b(?:value|path)\\s*=\\s*(\\{[^}]*}|\"[^\"]*\")"
    );
    private static final Pattern REQUEST_METHOD_PATTERN = Pattern.compile("RequestMethod\\.(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)");
    private static final Pattern QUOTED_STRING_PATTERN = Pattern.compile("\"([^\"]*)\"");
    private static final Pattern METHOD_DECLARATION_PATTERN = Pattern.compile(
            "(?ms)^\\s*"
                    + "(?:(?:public|protected|private|static|final|synchronized|abstract|default)\\s+)*"
                    + "(?:<[^>]+>\\s+)?"
                    + "[\\w$.<>\\[\\], ?]+\\s+"
                    + "(\\w+)\\s*"
                    + "\\([^;{}]*?\\)\\s*"
                    + "(?:throws\\s+[\\w$.,\\s]+)?\\{"
    );
    private static final Pattern CONTROLLER_ANNOTATION_PATTERN = Pattern.compile("@(?:RestController|Controller)\\b");
    private static final Pattern BLANK_LINE_PATTERN = Pattern.compile("(?m)^\\s*$");

    @Override
    public boolean supports(ProjectAnalysisContext context) {
        return context.projectType() == ProjectType.SPRING_BOOT || !context.javaFiles().isEmpty();
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
            ControllerDeclaration controller = findControllerDeclaration(content, file);
            if (controller == null) {
                return;
            }
            String controllerClass = controller.className();
            List<String> classPrefixes = controller.classPaths();
            Matcher mappingMatcher = METHOD_MAPPING_PATTERN.matcher(content);
            while (mappingMatcher.find()) {
                if (mappingMatcher.start() < controller.classStart()) {
                    log.debug("Spring接口解析跳过类级映射注解：文件={}，行={}，注解={}",
                            file.relativePath(),
                            lineNumber(content, mappingMatcher.start()),
                            contentLine(content, lineNumber(content, mappingMatcher.start()))
                    );
                    continue;
                }
                String annotation = mappingMatcher.group(1);
                String mappingBody = mappingMatcher.group(2);
                MethodDeclaration handlerMethod = findNextMethodDeclaration(content, mappingMatcher.end());
                if (handlerMethod == null) {
                    log.warn("Spring接口解析跳过注解：未找到对应的处理方法，文件={}，行={}，注解={}",
                            file.relativePath(),
                            lineNumber(content, mappingMatcher.start()),
                            contentLine(content, lineNumber(content, mappingMatcher.start()))
                    );
                    continue;
                }
                List<String> httpMethods = httpMethods(annotation, mappingBody);
                List<String> paths = joinPaths(classPrefixes, extractPaths(mappingBody));
                int line = lineNumber(content, mappingMatcher.start());
                List<EvidenceRef> evidenceRefs = buildEndpointEvidence(context, file, content, line, handlerMethod);
                evidenceRefs.forEach(result::addEvidence);
                for (String httpMethod : httpMethods) {
                    for (String path : paths) {
                        String endpointId = context.repoId() + ":ENDPOINT:" + httpMethod + ":" + path + ":" + controllerClass + "." + handlerMethod.name();
                        CodeEndpoint endpoint = new CodeEndpoint(
                                endpointId,
                                httpMethod,
                                path,
                                controllerClass,
                                handlerMethod.name(),
                                file.relativePath(),
                                line,
                                evidenceRefs
                        );
                        result.addEndpoint(endpoint);
                        addEndpointGraph(context, file, result, controller, handlerMethod, endpointId, httpMethod, path, evidenceRefs);
                    }
                }
            }
        } catch (IOException ex) {
            log.warn("Spring接口解析失败：读取文件异常，文件={}，原因={}", file.relativePath(), ex.getMessage(), ex);
        }
    }

    private List<EvidenceRef> buildEndpointEvidence(
            ProjectAnalysisContext context,
            SourceFile file,
            String content,
            int annotationLine,
            MethodDeclaration handlerMethod
    ) {
        EvidenceRef annotationEvidence = new EvidenceRef(
                context.repoId() + ":EV:spring_endpoint_annotation:" + file.relativePath() + ":" + annotationLine,
                file.relativePath(),
                annotationLine,
                annotationLine,
                contentLine(content, annotationLine),
                "spring_mapping_annotation",
                0.88
        );
        EvidenceRef methodEvidence = new EvidenceRef(
                context.repoId() + ":EV:spring_endpoint_handler:" + file.relativePath() + ":" + handlerMethod.line(),
                file.relativePath(),
                handlerMethod.line(),
                handlerMethod.line(),
                handlerMethod.signature(),
                "spring_handler_method",
                0.78
        );
        log.debug("Spring接口证据构建完成：文件={}，注解行={}，方法行={}，方法={}",
                file.relativePath(),
                annotationLine,
                handlerMethod.line(),
                handlerMethod.name()
        );
        return List.of(annotationEvidence, methodEvidence);
    }

    private void addEndpointGraph(
            ProjectAnalysisContext context,
            SourceFile file,
            CodeParseResult.Builder result,
            ControllerDeclaration controller,
            MethodDeclaration handlerMethod,
            String endpointId,
            String httpMethod,
            String path,
            List<EvidenceRef> evidenceRefs
    ) {
        String controllerNodeId = controllerNodeId(context, file, controller.className());
        String methodNodeId = methodNodeId(context, file, handlerMethod.name());
        EvidenceRef controllerEvidence = new EvidenceRef(
                context.repoId() + ":EV:spring_controller:" + file.relativePath() + ":" + controller.classLine(),
                file.relativePath(),
                controller.classLine(),
                controller.classLine(),
                controller.className(),
                "spring_controller_class",
                0.72
        );
        List<EvidenceRef> controllerEvidenceRefs = List.of(controllerEvidence);
        result.addEvidence(controllerEvidence);
        result.addNode(new CodeNode(
                controllerNodeId,
                "Controller Class",
                controller.className(),
                controller.className(),
                controllerEvidenceRefs
        ));
        result.addNode(new CodeNode(
                methodNodeId,
                "Handler Method",
                handlerMethod.name(),
                controller.className() + "." + handlerMethod.name(),
                evidenceRefs
        ));
        result.addNode(new CodeNode(
                endpointId,
                "API Endpoint",
                httpMethod + " " + path,
                controller.className() + "." + handlerMethod.name(),
                evidenceRefs
        ));
        result.addEdge(new CodeEdge(
                context.repoId() + ":EDGE:DECLARES:" + controller.className() + ":" + handlerMethod.name(),
                controllerNodeId,
                methodNodeId,
                "DECLARES",
                0.78,
                evidenceRefs
        ));
        result.addEdge(new CodeEdge(
                context.repoId() + ":EDGE:MAPS_TO_ENDPOINT:" + controller.className() + "." + handlerMethod.name() + ":" + endpointId,
                methodNodeId,
                endpointId,
                "MAPS_TO_ENDPOINT",
                0.88,
                evidenceRefs
        ));
        log.debug("Spring接口图谱节点构建完成：Controller={}，方法={}，接口={} {}",
                controller.className(),
                handlerMethod.name(),
                httpMethod,
                path
        );
    }

    private String controllerNodeId(ProjectAnalysisContext context, SourceFile file, String controllerClass) {
        return context.repoId() + ":CONTROLLER:" + file.relativePath() + "#" + controllerClass;
    }

    private String methodNodeId(ProjectAnalysisContext context, SourceFile file, String handlerMethod) {
        return context.repoId() + ":METHOD:" + file.relativePath() + "#" + handlerMethod;
    }

    private ControllerDeclaration findControllerDeclaration(String content, SourceFile file) {
        Matcher classMatcher = CLASS_NAME_PATTERN.matcher(content);
        if (!classMatcher.find()) {
            log.debug("Spring Controller识别跳过：未找到Java类声明，文件={}", file.relativePath());
            return null;
        }

        String className = classMatcher.group(1);
        int classStart = classMatcher.start();
        int classLine = lineNumber(content, classStart);
        String classAnnotationBlock = classAnnotationBlock(content, classStart);
        if (!isController(content, file, className, classAnnotationBlock)) {
            return null;
        }

        List<String> classPaths = extractPaths(firstGroup(CLASS_MAPPING_PATTERN, classAnnotationBlock));
        log.debug("Spring Controller声明识别完成：类={}，行={}，类级路径={}，文件={}",
                className,
                classLine,
                classPaths,
                file.relativePath()
        );
        return new ControllerDeclaration(className, classLine, classStart, classPaths);
    }

    private boolean isController(String content, SourceFile file, String className, String classAnnotationBlock) {
        if (CONTROLLER_ANNOTATION_PATTERN.matcher(classAnnotationBlock).find()) {
            log.debug("Spring Controller识别成功：发现@Controller或@RestController，类={}，文件={}",
                    className,
                    file.relativePath()
            );
            return true;
        }

        if (CLASS_MAPPING_PATTERN.matcher(classAnnotationBlock).find()) {
            log.info("Spring Controller识别成功：类上存在@RequestMapping但没有@Controller/@RestController，类={}，文件={}",
                    className,
                    file.relativePath()
            );
            return true;
        }

        if (className.endsWith("Controller") && content.contains("@RequestMapping")) {
            log.info("Spring Controller识别成功：类名以Controller结尾且存在@RequestMapping，类={}，文件={}",
                    className,
                    file.relativePath()
            );
            return true;
        }

        log.debug("Spring Controller识别跳过：不是Controller类，类={}，文件={}", className, file.relativePath());
        return false;
    }

    private String classAnnotationBlock(String content, int classStart) {
        String beforeClass = content.substring(0, classStart);
        int blockStart = 0;
        Matcher blankLineMatcher = BLANK_LINE_PATTERN.matcher(beforeClass);
        while (blankLineMatcher.find()) {
            blockStart = blankLineMatcher.end();
        }
        return content.substring(blockStart, classStart);
    }

    private String firstGroup(Pattern pattern, String content) {
        Matcher matcher = pattern.matcher(content);
        return matcher.find() ? matcher.group(1) : null;
    }

    private MethodDeclaration findNextMethodDeclaration(String content, int offset) {
        Matcher matcher = METHOD_DECLARATION_PATTERN.matcher(content);
        if (!matcher.find(offset)) {
            return null;
        }
        int start = matcher.start();
        int openBrace = matcher.end() - 1;
        String signature = content.substring(start, openBrace).replaceAll("\\s+", " ").trim();
        int line = lineNumber(content, start);
        log.debug("Spring接口处理方法识别成功：方法={}，行={}，签名={}", matcher.group(1), line, signature);
        return new MethodDeclaration(matcher.group(1), line, signature);
    }

    private List<String> httpMethods(String annotation, String mappingBody) {
        return switch (annotation) {
            case "GetMapping" -> List.of("GET");
            case "PostMapping" -> List.of("POST");
            case "PutMapping" -> List.of("PUT");
            case "DeleteMapping" -> List.of("DELETE");
            case "PatchMapping" -> List.of("PATCH");
            default -> requestMappingMethods(mappingBody);
        };
    }

    private List<String> requestMappingMethods(String mappingBody) {
        if (mappingBody == null) {
            return List.of("ANY");
        }

        List<String> methods = new ArrayList<>();
        Matcher methodMatcher = REQUEST_METHOD_PATTERN.matcher(mappingBody);
        while (methodMatcher.find()) {
            methods.add(methodMatcher.group(1));
        }
        if (methods.isEmpty()) {
            log.info("Spring接口HTTP方法未指定，将按ANY处理，注解内容={}", mappingBody);
            return List.of("ANY");
        }
        return new ArrayList<>(new LinkedHashSet<>(methods));
    }

    private List<String> extractPaths(String annotationBody) {
        if (annotationBody == null || annotationBody.isBlank()) {
            return List.of("");
        }

        List<String> paths = new ArrayList<>();
        Matcher attributeMatcher = MAPPING_PATH_ATTRIBUTE_PATTERN.matcher(annotationBody);
        while (attributeMatcher.find()) {
            addQuotedPaths(attributeMatcher.group(1), paths);
        }
        if (!paths.isEmpty()) {
            return uniquePaths(paths);
        }

        String trimmedBody = annotationBody.trim();
        if (trimmedBody.startsWith("{")) {
            int arrayEnd = trimmedBody.indexOf('}');
            if (arrayEnd >= 0) {
                addQuotedPaths(trimmedBody.substring(0, arrayEnd + 1), paths);
            }
        } else if (trimmedBody.startsWith("\"")) {
            Matcher directPath = QUOTED_STRING_PATTERN.matcher(trimmedBody);
            if (directPath.find()) {
                paths.add(directPath.group(1));
            }
        }

        if (paths.isEmpty()) {
            log.warn("Spring接口路径解析未提取到路径，注解内容={}", annotationBody);
        }
        return uniquePaths(paths);
    }

    private void addQuotedPaths(String source, List<String> paths) {
        Matcher quoted = QUOTED_STRING_PATTERN.matcher(source);
        while (quoted.find()) {
            paths.add(quoted.group(1));
        }
    }

    private List<String> uniquePaths(List<String> paths) {
        if (paths.isEmpty()) {
            return List.of("");
        }
        return new ArrayList<>(new LinkedHashSet<>(paths));
    }

    private List<String> joinPaths(List<String> prefixes, List<String> paths) {
        List<String> safePrefixes = emptyToRootPath(prefixes, "类级路径");
        List<String> safePaths = emptyToRootPath(paths, "方法级路径");
        List<String> joinedPaths = new ArrayList<>();
        for (String prefix : safePrefixes) {
            for (String path : safePaths) {
                joinedPaths.add(joinSinglePath(prefix, path));
            }
        }
        List<String> uniqueJoinedPaths = uniquePaths(joinedPaths);
        log.debug("Spring接口路径组合完成：类级路径数量={}，方法级路径数量={}，结果数量={}",
                safePrefixes.size(),
                safePaths.size(),
                uniqueJoinedPaths.size()
        );
        return uniqueJoinedPaths;
    }

    private List<String> emptyToRootPath(List<String> paths, String pathSource) {
        if (paths == null || paths.isEmpty()) {
            log.warn("Spring接口路径组合收到空{}，将按根路径处理", pathSource);
            return List.of("");
        }
        return paths;
    }

    private String joinSinglePath(String prefix, String path) {
        String normalizedPrefix = normalizePath(prefix);
        String normalizedPath = normalizePath(path);
        String joinedPath;
        if (normalizedPrefix.equals("/")) {
            joinedPath = normalizedPath;
        } else if (normalizedPath.equals("/")) {
            joinedPath = normalizedPrefix;
        } else {
            joinedPath = normalizePath(normalizedPrefix + "/" + normalizedPath);
        }
        log.debug("Spring接口路径拼接完成：原始前缀={}，原始路径={}，结果={}", prefix, path, joinedPath);
        return joinedPath;
    }

    private String normalizePath(String path) {
        if (path == null || path.isBlank()) {
            return "/";
        }
        String normalized = path.trim().replace('\\', '/');
        normalized = normalized.replaceAll("/{2,}", "/");
        if (!normalized.startsWith("/")) {
            normalized = "/" + normalized;
        }
        if (normalized.length() > 1) {
            normalized = normalized.replaceAll("/+$", "");
        }
        if (!normalized.equals(path)) {
            log.debug("Spring接口路径已规范化：原始路径={}，规范路径={}", path, normalized);
        }
        return normalized;
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

    private String contentLine(String content, int lineNumber) {
        String[] lines = content.split("\\R");
        if (lineNumber <= 0 || lineNumber > lines.length) {
            return "";
        }
        return lines[lineNumber - 1].trim();
    }

    private record MethodDeclaration(String name, int line, String signature) {
    }

    private record ControllerDeclaration(String className, int classLine, int classStart, List<String> classPaths) {
    }
}
