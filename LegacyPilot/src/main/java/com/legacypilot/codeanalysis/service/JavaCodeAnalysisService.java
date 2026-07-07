package com.legacypilot.codeanalysis.service;

import com.legacypilot.codeanalysis.context.ProjectAnalysisContext;
import com.legacypilot.codeanalysis.context.SourceFile;
import com.legacypilot.codeanalysis.context.SourceFileType;
import com.legacypilot.codeanalysis.detector.ProjectType;
import com.legacypilot.codeanalysis.detector.ProjectTypeDetector;
import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.entity.CodeEdge;
import com.legacypilot.codeanalysis.entity.CodeEndpoint;
import com.legacypilot.codeanalysis.entity.CodeGraphSummary;
import com.legacypilot.codeanalysis.entity.CodeNode;
import com.legacypilot.codeanalysis.entity.EvidenceRef;
import com.legacypilot.codeanalysis.parser.CodeParseResult;
import com.legacypilot.codeanalysis.parser.CodeParser;
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

/**
 * Java/Spring-specific analysis orchestrator.
 *
 * Parser implementations stay independent and can be replaced or extended
 * without changing this service boundary.
 */
@Service
public class JavaCodeAnalysisService {
    private static final Logger log = LoggerFactory.getLogger(JavaCodeAnalysisService.class);

    private final ProjectTypeDetector projectTypeDetector;
    private final List<CodeParser> parsers;

    public JavaCodeAnalysisService(ProjectTypeDetector projectTypeDetector, List<CodeParser> parsers) {
        this.projectTypeDetector = projectTypeDetector;
        this.parsers = List.copyOf(parsers);
    }

    public CodeAnalysisResult analyze(String repoId, String localRepoPath) {
        Path repositoryRoot = Path.of(localRepoPath).toAbsolutePath().normalize();
        if (!Files.isDirectory(repositoryRoot)) {
            throw new ResponseStatusException(BAD_REQUEST, "localRepoPath must be an existing directory.");
        }

        ProjectType projectType = projectTypeDetector.detect(repositoryRoot);
        ProjectAnalysisContext context = new ProjectAnalysisContext(
                repoId,
                repositoryRoot,
                projectType,
                scanSourceFiles(repositoryRoot)
        );

        List<CodeNode> nodes = new ArrayList<>();
        List<CodeEdge> edges = new ArrayList<>();
        List<CodeEndpoint> endpoints = new ArrayList<>();
        List<EvidenceRef> evidenceRefs = new ArrayList<>();
        int classCount = 0;
        int methodCount = 0;

        for (CodeParser parser : parsers) {
            if (!parser.supports(context)) {
                continue;
            }
            CodeParseResult contribution = parser.parse(context);
            nodes.addAll(contribution.nodes());
            edges.addAll(contribution.edges());
            endpoints.addAll(contribution.endpoints());
            evidenceRefs.addAll(contribution.evidenceRefs());
            classCount += contribution.classCount();
            methodCount += contribution.methodCount();
        }

        List<CodeNode> uniqueNodes = distinctById(nodes, CodeNode::nodeId);
        List<CodeEdge> uniqueEdges = distinctById(edges, CodeEdge::edgeId);
        List<CodeEndpoint> uniqueEndpoints = distinctById(endpoints, CodeEndpoint::endpointId);
        List<EvidenceRef> uniqueEvidenceRefs = distinctById(evidenceRefs, EvidenceRef::evidenceId);

        CodeGraphSummary summary = new CodeGraphSummary(
                repoId,
                projectType.name(),
                uniqueNodes.size(),
                uniqueEdges.size(),
                classCount,
                methodCount,
                uniqueEndpoints.size()
        );

        return new CodeAnalysisResult(
                summary,
                uniqueEndpoints,
                uniqueNodes,
                uniqueEdges,
                uniqueEvidenceRefs
        );
    }

    private <T> List<T> distinctById(List<T> items, java.util.function.Function<T, String> identity) {
        Map<String, T> uniqueItems = new LinkedHashMap<>();
        for (T item : items) {
            uniqueItems.putIfAbsent(identity.apply(item), item);
        }
        return List.copyOf(uniqueItems.values());
    }

    private List<SourceFile> scanSourceFiles(Path repositoryRoot) {
        List<SourceFile> sourceFiles = new ArrayList<>();
        try {
            Files.walkFileTree(repositoryRoot, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    if (!dir.equals(repositoryRoot) && isIgnoredPath(repositoryRoot, dir)) {
                        log.debug("代码分析跳过目录：{}", toRelativePath(repositoryRoot, dir));
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (!attrs.isRegularFile() || isIgnoredPath(repositoryRoot, file)) {
                        return FileVisitResult.CONTINUE;
                    }
                    sourceFiles.add(new SourceFile(
                            file,
                            toRelativePath(repositoryRoot, file),
                            sourceFileType(file)
                    ));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exception) {
                    log.warn("代码分析跳过无法访问的文件：文件={}，原因={}", file, exception.getMessage());
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException exception) {
            log.warn("代码分析扫描源码文件失败：目录={}，原因={}", repositoryRoot, exception.getMessage(), exception);
            throw new ResponseStatusException(BAD_REQUEST, "Failed to scan repository source files.");
        }
        log.info("代码分析源码扫描完成：目录={}，文件数量={}", repositoryRoot, sourceFiles.size());
        return List.copyOf(sourceFiles);
    }

    private boolean isIgnoredPath(Path root, Path path) {
        Path relative = root.relativize(path);
        for (Path part : relative) {
            String name = part.toString();
            if (name.equals(".git")
                    || name.equals(".gitnexus")
                    || name.equals(".idea")
                    || name.equals(".vscode")
                    || name.equals(".venv")
                    || name.equals("venv")
                    || name.equals(".pytest_cache")
                    || name.equals("__pycache__")
                    || name.equals("node_modules")
                    || name.equals("target")
                    || name.equals("build")
                    || name.equals("dist")) {
                return true;
            }
        }
        return false;
    }

    private String toRelativePath(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }

    private SourceFileType sourceFileType(Path path) {
        String lower = path.getFileName().toString().toLowerCase();
        if (lower.endsWith(".java")) {
            return SourceFileType.JAVA;
        }
        if (lower.endsWith(".xml")) {
            return SourceFileType.XML;
        }
        if (lower.endsWith(".yml") || lower.endsWith(".yaml")) {
            return SourceFileType.YAML;
        }
        if (lower.endsWith(".properties")) {
            return SourceFileType.PROPERTIES;
        }
        return SourceFileType.OTHER;
    }
}
