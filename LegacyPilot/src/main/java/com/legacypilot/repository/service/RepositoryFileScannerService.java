package com.legacypilot.repository.service;

import com.legacypilot.repository.dto.RepositoryFilesResponse;
import com.legacypilot.repository.entity.RepositoryIndex;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileVisitResult;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

/**
 * Scans a connected repository directory and returns a lightweight file summary.
 *
 * This service is intentionally limited to filesystem scanning. It does not own
 * project IDs, repository IDs, Git validation, or code graph analysis.
 */
@Service
public class RepositoryFileScannerService {

    /**
     * Reads source/config/build/markdown files from a repository local path.
     */
    public RepositoryFilesResponse scanRepositoryFiles(RepositoryIndex repository) {
        if (repository.localRepoPath() == null || repository.localRepoPath().isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "Repository does not have a local path.");
        }

        Path root = Path.of(repository.localRepoPath()).toAbsolutePath().normalize();
        if (!Files.isDirectory(root)) {
            throw new ResponseStatusException(BAD_REQUEST, "Repository local path is not available.");
        }

        List<String> javaFiles = new ArrayList<>();
        List<String> pythonFiles = new ArrayList<>();
        List<String> configFiles = new ArrayList<>();
        List<String> buildFiles = new ArrayList<>();
        List<String> markdownFiles = new ArrayList<>();

        FileCounter fileCounter = new FileCounter();
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    if (!dir.equals(root) && isIgnoredPath(root, dir)) {
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (!attrs.isRegularFile() || isIgnoredPath(root, file)) {
                        return FileVisitResult.CONTINUE;
                    }
                    fileCounter.increment();

                String relativePath = toRelativePath(root, file);
                String lower = relativePath.toLowerCase();
                if (lower.endsWith(".java")) {
                    javaFiles.add(relativePath);
                } else if (lower.endsWith(".py")) {
                    pythonFiles.add(relativePath);
                } else if (isConfigFile(lower)) {
                    configFiles.add(relativePath);
                } else if (isBuildFile(lower)) {
                    buildFiles.add(relativePath);
                } else if (lower.endsWith(".md") || lower.endsWith(".markdown")) {
                    markdownFiles.add(relativePath);
                }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exception) {
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException exception) {
            throw new ResponseStatusException(BAD_REQUEST, "Failed to scan repository files.");
        }

        return new RepositoryFilesResponse(
                repository.repoId(),
                repository.localRepoPath(),
                fileCounter.value(),
                javaFiles,
                pythonFiles,
                configFiles,
                buildFiles,
                markdownFiles
        );
    }

    /**
     * Keeps the scan focused on project source files instead of Git internals
     * and generated dependency/build folders.
     */
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

    /**
     * Normalizes Windows separators to forward slashes so API output is stable.
     */
    private String toRelativePath(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }

    private boolean isConfigFile(String lowerPath) {
        return lowerPath.endsWith(".yml")
                || lowerPath.endsWith(".yaml")
                || lowerPath.endsWith(".properties")
                || lowerPath.endsWith(".json")
                || lowerPath.endsWith(".toml")
                || lowerPath.endsWith(".ini")
                || lowerPath.endsWith(".env")
                || lowerPath.endsWith(".xml")
                || lowerPath.endsWith(".gitignore")
                || lowerPath.endsWith("requirements.txt");
    }

    private boolean isBuildFile(String lowerPath) {
        return lowerPath.endsWith("pom.xml")
                || lowerPath.endsWith("build.gradle")
                || lowerPath.endsWith("build.gradle.kts")
                || lowerPath.endsWith("settings.gradle")
                || lowerPath.endsWith("settings.gradle.kts")
                || lowerPath.endsWith("package.json")
                || lowerPath.endsWith("pnpm-lock.yaml")
                || lowerPath.endsWith("yarn.lock")
                || lowerPath.endsWith("package-lock.json")
                || lowerPath.endsWith("pyproject.toml")
                || lowerPath.endsWith("setup.py");
    }

    private static class FileCounter {
        private int value;

        private void increment() {
            value++;
        }

        private int value() {
            return value;
        }
    }
}
