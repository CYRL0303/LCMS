package com.legacypilot.project.service;

import com.legacypilot.project.dto.CreateProjectRequest;
import com.legacypilot.project.entity.LegacyProject;
import com.legacypilot.persistence.jdbc.ProjectJdbcRepository;
import java.time.Instant;
import java.util.Collection;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.CONFLICT;
import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Project lifecycle service.
 */
@Service
public class ProjectService {
    private static final String DEFAULT_OWNER_ID = "local-dev";

    private final ProjectJdbcRepository projectJdbcRepository;

    public ProjectService(ProjectJdbcRepository projectJdbcRepository) {
        this.projectJdbcRepository = projectJdbcRepository;
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
        if (projectJdbcRepository.findByOwnerIdAndName(DEFAULT_OWNER_ID, name).isPresent()) {
            throw new ResponseStatusException(CONFLICT, "Project name already exists.");
        }
        String projectId = newId("PROJ");
        LegacyProject project = new LegacyProject(
                projectId,
                name,
                repositoryUrl,
                defaultValue(defaultBranch, "main"),
                createdAt
        );
        projectJdbcRepository.insert(project);
        return project;
    }

    public LegacyProject findOrCreateProject(String name, String repositoryUrl, String defaultBranch, String createdAt) {
        requireText(name, "name");
        return projectJdbcRepository.findByOwnerIdAndName(DEFAULT_OWNER_ID, name)
                .orElseGet(() -> createProject(name, repositoryUrl, defaultBranch, createdAt));
    }

    public Collection<LegacyProject> listProjects() {
        return projectJdbcRepository.findAll();
    }

    public LegacyProject getProject(String projectId) {
        return projectJdbcRepository.findById(projectId)
                .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Project not found: " + projectId));
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
