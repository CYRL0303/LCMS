package com.legacypilot.service;

import com.legacypilot.dto.CodeKnowledgeGraphSnapshotResponse;
import com.legacypilot.dto.CodeKnowledgeIndexRequest;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_GATEWAY;

/**
 * HTTP client for the LCMS Python code knowledge service.
 *
 * This service owns the JSON contract translation from Java backend concepts
 * to the FastAPI /v1/repos/index endpoint. It is intentionally not wired into
 * AnalysisService yet, so it can be tested independently before changing the
 * onboarding flow.
 */
@Service
public class CodeKnowledgeClient {
    private static final String DEFAULT_CONTRACT_VERSION = "1.0.0";
    private static final String JAVA_LANGUAGE = "java";
    private static final String PYTHON_LANGUAGE = "python";
    private static final String GENERIC_LANGUAGE = "generic";

    private final RestClient restClient;
    private final String baseUrl;

    public CodeKnowledgeClient(
            RestClient.Builder restClientBuilder,
            @Value("${legacypilot.code-knowledge.base-url:http://127.0.0.1:8001}") String baseUrl
    ) {
        this.baseUrl = baseUrl;
        this.restClient = restClientBuilder.baseUrl(baseUrl).build();
    }

    /**
     * Requests a repository graph snapshot from Python using the minimum data
     * Java already owns after local-project onboarding.
     */
    public CodeKnowledgeGraphSnapshotResponse indexRepository(String repoId, String localRepoPath) {
        String languageHint = detectLanguageHint(localRepoPath);
        return indexRepository(repoId, localRepoPath, languageHint, defaultParserProfile(languageHint));
    }

    /**
     * Requests a graph snapshot with an explicit language/parser choice.
     *
     * This overload is useful once the frontend lets users pick a stack, or
     * when mixed-language repositories need a deliberate parser profile.
     */
    public CodeKnowledgeGraphSnapshotResponse indexRepository(
            String repoId,
            String localRepoPath,
            String languageHint,
            String parserProfile
    ) {
        CodeKnowledgeIndexRequest request = new CodeKnowledgeIndexRequest(
                repoId,
                localRepoPath,
                languageHint,
                parserProfile,
                DEFAULT_CONTRACT_VERSION
        );

        try {
            return restClient.post()
                    .uri("/v1/repos/index")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(CodeKnowledgeGraphSnapshotResponse.class);
        } catch (RestClientException exception) {
            throw new ResponseStatusException(
                    BAD_GATEWAY,
                    "Failed to call code knowledge service at " + baseUrl + ". Is the Python FastAPI service running?",
                    exception
            );
        }
    }

    /**
     * Chooses a first-pass language hint by counting source file extensions.
     *
     * The project focus is Java/Spring legacy code, but local testing may use
     * Python repositories. This keeps the Python service request honest without
     * requiring extra input from the user.
     */
    private String detectLanguageHint(String localRepoPath) {
        Path root = Path.of(localRepoPath).toAbsolutePath().normalize();
        if (!Files.isDirectory(root)) {
            return GENERIC_LANGUAGE;
        }

        try (var stream = Files.walk(root)) {
            LanguageCounts counts = stream
                    .filter(Files::isRegularFile)
                    .filter(path -> !isIgnoredPath(root, path))
                    .map(path -> path.getFileName().toString().toLowerCase())
                    .collect(LanguageCounts::new, LanguageCounts::accept, LanguageCounts::combine);

            if (counts.javaFiles > 0 && counts.javaFiles >= counts.pythonFiles) {
                return JAVA_LANGUAGE;
            }
            if (counts.pythonFiles > 0) {
                return PYTHON_LANGUAGE;
            }
        } catch (IOException ignored) {
            return GENERIC_LANGUAGE;
        }

        return GENERIC_LANGUAGE;
    }

    private boolean isIgnoredPath(Path root, Path path) {
        Path relative = root.relativize(path);
        for (Path part : relative) {
            String name = part.toString();
            if (name.equals(".git")
                    || name.equals(".idea")
                    || name.equals(".vscode")
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

    private String defaultParserProfile(String languageHint) {
        return switch (languageHint) {
            case JAVA_LANGUAGE -> "spring-mybatis";
            case PYTHON_LANGUAGE -> "python-default";
            default -> "generic";
        };
    }

    private static class LanguageCounts {
        private int javaFiles;
        private int pythonFiles;

        private void accept(String fileName) {
            if (fileName.endsWith(".java")) {
                javaFiles++;
            } else if (fileName.endsWith(".py")) {
                pythonFiles++;
            }
        }

        private void combine(LanguageCounts other) {
            javaFiles += other.javaFiles;
            pythonFiles += other.pythonFiles;
        }
    }
}
