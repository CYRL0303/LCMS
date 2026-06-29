package com.legacypilot.project.service;

import com.legacypilot.project.dto.CreateProjectRequest;
import com.legacypilot.project.entity.LegacyProject;
import com.legacypilot.workspace.store.InMemoryWorkspaceStore;
import java.time.Instant;
import java.util.Collection;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Project lifecycle service.
 */
@Service
public class ProjectService {
    private final InMemoryWorkspaceStore store;

    public ProjectService(InMemoryWorkspaceStore store) {
        this.store = store;
    }

    public LegacyProject createProject(CreateProjectRequest request) {
        requireText(request.name(), "name");
        return createProject(
                request.name(),
                request.repositoryUrl(),
                defaultValue(request.defaultBranch(), "main"),
                now()
        );
    }

    public LegacyProject createProject(String name, String repositoryUrl, String defaultBranch, String createdAt) {
        requireText(name, "name");
        String projectId = newId("PROJ");
        LegacyProject project = new LegacyProject(
                projectId,
                name,
                repositoryUrl,
                defaultValue(defaultBranch, "main"),
                createdAt
        );
        store.projects().put(projectId, project);
        return project;
    }

    public Collection<LegacyProject> listProjects() {
        return store.projects().values();
    }

    public LegacyProject getProject(String projectId) {
        LegacyProject project = store.projects().get(projectId);
        if (project == null) {
            throw new ResponseStatusException(NOT_FOUND, "Project not found: " + projectId);
        }
        return project;
    }

    private void requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new ResponseStatusException(BAD_REQUEST, fieldName + " is required.");
        }
    }

    private String defaultValue(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value;
    }

    private String newId(String prefix) {
        return prefix + "-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    private String now() {
        return Instant.now().toString();
    }
}
