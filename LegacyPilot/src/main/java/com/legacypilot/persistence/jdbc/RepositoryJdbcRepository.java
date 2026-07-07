package com.legacypilot.persistence.jdbc;

import com.legacypilot.repository.entity.RepositoryIndex;
import com.legacypilot.repository.entity.RepositorySourceType;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class RepositoryJdbcRepository {
    private final JdbcTemplate jdbcTemplate;

    public RepositoryJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(RepositoryIndex repository) {
        jdbcTemplate.update(
                """
                INSERT INTO repository_index (
                    repo_id, project_id, source_type, repository_url, local_repo_path,
                    branch_name, commit_sha, graph_id, task_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                repository.repoId(),
                repository.projectId(),
                repository.sourceType().name(),
                repository.repositoryUrl(),
                repository.localRepoPath(),
                repository.branch(),
                repository.commitSha(),
                repository.graphId(),
                repository.taskId(),
                repository.createdAt()
        );
    }

    public void update(RepositoryIndex repository) {
        jdbcTemplate.update(
                """
                UPDATE repository_index
                SET source_type = ?,
                    repository_url = ?,
                    local_repo_path = ?,
                    branch_name = ?,
                    commit_sha = ?,
                    graph_id = ?,
                    task_id = ?
                WHERE repo_id = ?
                """,
                repository.sourceType().name(),
                repository.repositoryUrl(),
                repository.localRepoPath(),
                repository.branch(),
                repository.commitSha(),
                repository.graphId(),
                repository.taskId(),
                repository.repoId()
        );
    }

    public Optional<RepositoryIndex> findById(String repoId) {
        List<RepositoryIndex> repositories = jdbcTemplate.query(
                """
                SELECT repo_id, project_id, source_type, repository_url, local_repo_path,
                       branch_name, commit_sha, graph_id, task_id, created_at
                FROM repository_index
                WHERE repo_id = ?
                """,
                this::mapRow,
                repoId
        );
        return repositories.stream().findFirst();
    }

    public Optional<RepositoryIndex> findExisting(
            String projectId,
            RepositorySourceType sourceType,
            String localRepoPath,
            String repositoryUrl,
            String branch,
            String commitSha
    ) {
        List<RepositoryIndex> repositories = jdbcTemplate.query(
                """
                SELECT repo_id, project_id, source_type, repository_url, local_repo_path,
                       branch_name, commit_sha, graph_id, task_id, created_at
                FROM repository_index
                WHERE project_id = ?
                  AND source_type = ?
                  AND local_repo_path <=> ?
                  AND repository_url <=> ?
                  AND branch_name <=> ?
                  AND commit_sha <=> ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                this::mapRow,
                projectId,
                sourceType.name(),
                localRepoPath,
                repositoryUrl,
                branch,
                commitSha
        );
        return repositories.stream().findFirst();
    }

    public Optional<RepositoryIndex> findLatestByProjectId(String projectId) {
        List<RepositoryIndex> repositories = jdbcTemplate.query(
                """
                SELECT repo_id, project_id, source_type, repository_url, local_repo_path,
                       branch_name, commit_sha, graph_id, task_id, created_at
                FROM repository_index
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                this::mapRow,
                projectId
        );
        return repositories.stream().findFirst();
    }

    private RepositoryIndex mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new RepositoryIndex(
                rs.getString("repo_id"),
                rs.getString("project_id"),
                RepositorySourceType.valueOf(rs.getString("source_type")),
                rs.getString("repository_url"),
                rs.getString("local_repo_path"),
                rs.getString("branch_name"),
                rs.getString("commit_sha"),
                rs.getString("graph_id"),
                rs.getString("task_id"),
                rs.getString("created_at")
        );
    }
}
