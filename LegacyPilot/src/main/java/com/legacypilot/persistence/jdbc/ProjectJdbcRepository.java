package com.legacypilot.persistence.jdbc;

import com.legacypilot.project.entity.LegacyProject;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProjectJdbcRepository {
    private final JdbcTemplate jdbcTemplate;

    public ProjectJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(LegacyProject project) {
        jdbcTemplate.update(
                """
                INSERT INTO legacy_project (project_id, owner_id, name, repository_url, default_branch, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                project.projectId(),
                "local-dev",
                project.name(),
                project.repositoryUrl(),
                project.defaultBranch(),
                project.createdAt()
        );
    }

    public List<LegacyProject> findAll() {
        return jdbcTemplate.query(
                """
                SELECT project_id, name, repository_url, default_branch, created_at
                FROM legacy_project
                ORDER BY created_at DESC
                """,
                this::mapRow
        );
    }

    public Optional<LegacyProject> findById(String projectId) {
        List<LegacyProject> projects = jdbcTemplate.query(
                """
                SELECT project_id, name, repository_url, default_branch, created_at
                FROM legacy_project
                WHERE project_id = ?
                """,
                this::mapRow,
                projectId
        );
        return projects.stream().findFirst();
    }

    public Optional<LegacyProject> findByOwnerIdAndName(String ownerId, String name) {
        List<LegacyProject> projects = jdbcTemplate.query(
                """
                SELECT project_id, name, repository_url, default_branch, created_at
                FROM legacy_project
                WHERE owner_id = ? AND name = ?
                """,
                this::mapRow,
                ownerId,
                name
        );
        return projects.stream().findFirst();
    }

    private LegacyProject mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new LegacyProject(
                rs.getString("project_id"),
                rs.getString("name"),
                rs.getString("repository_url"),
                rs.getString("default_branch"),
                rs.getString("created_at")
        );
    }
}
