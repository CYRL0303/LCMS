package com.legacypilot.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

/**
 * Small adapter around the local system Git executable.
 *
 * The first MVP does not clone repositories. It only validates a user-provided
 * local path and extracts stable Git metadata that later analysis must cite:
 * branch, commit SHA, local path, and optional origin URL.
 */
@Service
public class GitRepositoryService {
    private static final Duration GIT_TIMEOUT = Duration.ofSeconds(10);

    /**
     * Validates a local repository path and returns normalized Git metadata.
     *
     * The requested branch is treated as a safety check. If the user says they
     * want branch "main" but the local checkout is on "dev", the backend rejects
     * the request instead of silently analyzing the wrong code.
     */
    public LocalGitRepository inspectLocalRepository(String localRepoPath, String requestedBranch) {
        if (localRepoPath == null || localRepoPath.isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, "localRepoPath is required.");
        }

        Path repoPath = Path.of(localRepoPath).toAbsolutePath().normalize();
        if (!Files.isDirectory(repoPath)) {
            throw new ResponseStatusException(BAD_REQUEST, "localRepoPath must be an existing directory.");
        }

        // Confirms the directory is inside a Git working tree. This is more
        // robust than only checking for a .git folder because worktrees and some
        // repository layouts can store Git metadata differently.
        String isInsideWorkTree = runGit(repoPath, "rev-parse", "--is-inside-work-tree");
        if (!"true".equals(isInsideWorkTree.trim())) {
            throw new ResponseStatusException(BAD_REQUEST, "localRepoPath is not a Git working tree.");
        }

        // Detached HEAD is allowed because a future analysis may target a
        // specific commit instead of a named branch.
        String currentBranch = runGit(repoPath, "branch", "--show-current").trim();
        if (currentBranch.isBlank()) {
            currentBranch = "detached";
        }

        if (requestedBranch != null && !requestedBranch.isBlank() && !"detached".equals(currentBranch)) {
            if (!requestedBranch.equals(currentBranch)) {
                throw new ResponseStatusException(
                        BAD_REQUEST,
                        "Requested branch does not match local repository branch: " + currentBranch
                );
            }
        }

        String commitSha = runGit(repoPath, "rev-parse", "HEAD").trim();

        // A local-only repository may not have origin; that is acceptable for
        // local-path testing, so this command is allowed to return an empty
        // string.
        String repositoryUrl = runGitAllowEmpty(repoPath, "remote", "get-url", "origin").trim();

        return new LocalGitRepository(
                repoPath.toString(),
                repositoryUrl.isBlank() ? null : repositoryUrl,
                currentBranch,
                commitSha
        );
    }

    /**
     * Runs a Git command that must succeed with non-empty success semantics.
     */
    private String runGit(Path repoPath, String... args) {
        String output = runGitAllowEmpty(repoPath, args);
        if (output == null) {
            throw new ResponseStatusException(BAD_REQUEST, "Git command failed.");
        }
        return output;
    }

    /**
     * Runs a Git command and returns an empty string when Git exits non-zero.
     *
     * This behavior is useful for optional metadata such as origin URL. Hard
     * validation commands should call runGit instead.
     */
    private String runGitAllowEmpty(Path repoPath, String... args) {
        try {
            ProcessBuilder builder = new ProcessBuilder(command(args));
            builder.directory(repoPath.toFile());
            builder.redirectErrorStream(true);

            Process process = builder.start();
            boolean finished = process.waitFor(GIT_TIMEOUT.toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                throw new ResponseStatusException(BAD_REQUEST, "Git command timed out.");
            }

            String output = new String(process.getInputStream().readAllBytes());
            if (process.exitValue() != 0) {
                return "";
            }
            return output;
        } catch (IOException exception) {
            throw new ResponseStatusException(BAD_REQUEST, "Git is not available on this machine.");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(BAD_REQUEST, "Git command was interrupted.");
        }
    }

    /**
     * Builds a ProcessBuilder-safe command list instead of shell-concatenating
     * user input.
     */
    private List<String> command(String... args) {
        List<String> command = new java.util.ArrayList<>();
        command.add("git");
        command.addAll(List.of(args));
        return command;
    }

    /**
     * Normalized local Git metadata returned to AnalysisService.
     */
    public record LocalGitRepository(
            String localRepoPath,
            String repositoryUrl,
            String branch,
            String commitSha
    ) {
    }
}
