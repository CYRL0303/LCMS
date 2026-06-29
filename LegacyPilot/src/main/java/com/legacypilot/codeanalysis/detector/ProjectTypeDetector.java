package com.legacypilot.codeanalysis.detector;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Detects the dominant project type without owning parser behavior.
 */
@Component
public class ProjectTypeDetector {
    private static final Logger log = LoggerFactory.getLogger(ProjectTypeDetector.class);

    public ProjectType detect(Path repositoryRoot) {
        if (containsSpringBootSignal(repositoryRoot)) {
            return ProjectType.SPRING_BOOT;
        }
        if (Files.exists(repositoryRoot.resolve("pom.xml"))
                || Files.exists(repositoryRoot.resolve("build.gradle"))
                || Files.exists(repositoryRoot.resolve("build.gradle.kts"))) {
            return ProjectType.JAVA;
        }
        if (Files.exists(repositoryRoot.resolve("pyproject.toml"))
                || Files.exists(repositoryRoot.resolve("requirements.txt"))) {
            return ProjectType.PYTHON;
        }
        if (Files.exists(repositoryRoot.resolve("package.json"))) {
            return ProjectType.NODE;
        }
        return ProjectType.GENERIC;
    }

    private boolean containsSpringBootSignal(Path repositoryRoot) {
        AtomicBoolean found = new AtomicBoolean(false);
        AtomicInteger scannedJavaFiles = new AtomicInteger(0);
        try {
            Files.walkFileTree(repositoryRoot, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    if (!dir.equals(repositoryRoot) && isIgnoredPath(repositoryRoot, dir)) {
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (found.get() || scannedJavaFiles.get() >= 500) {
                        return FileVisitResult.TERMINATE;
                    }
                    if (!attrs.isRegularFile() || isIgnoredPath(repositoryRoot, file) || !file.toString().endsWith(".java")) {
                        return FileVisitResult.CONTINUE;
                    }
                    scannedJavaFiles.incrementAndGet();
                    if (containsSpringAnnotation(file)) {
                        found.set(true);
                        return FileVisitResult.TERMINATE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exception) {
                    log.warn("项目类型检测跳过无法访问的文件：文件={}，原因={}", file, exception.getMessage());
                    return FileVisitResult.CONTINUE;
                }
            });
            log.debug("项目类型检测完成：目录={}，扫描Java文件数量={}，发现Spring信号={}",
                    repositoryRoot,
                    scannedJavaFiles.get(),
                    found.get()
            );
            return found.get();
        } catch (IOException exception) {
            log.warn("项目类型检测扫描失败：目录={}，原因={}", repositoryRoot, exception.getMessage(), exception);
            return false;
        }
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

    private boolean containsSpringAnnotation(Path path) {
        try {
            String content = Files.readString(path);
            return content.contains("@SpringBootApplication")
                    || content.contains("@RestController")
                    || content.contains("@Controller");
        } catch (IOException exception) {
            log.warn("项目类型检测读取Java文件失败：文件={}，原因={}", path, exception.getMessage());
            return false;
        }
    }
}
