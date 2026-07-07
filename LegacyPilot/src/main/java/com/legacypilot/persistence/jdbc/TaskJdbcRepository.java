package com.legacypilot.persistence.jdbc;

import com.legacypilot.task.entity.AnalysisTask;
import com.legacypilot.task.entity.AnalysisTaskStatus;
import com.legacypilot.task.entity.AnalysisTaskType;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class TaskJdbcRepository {
    private final JdbcTemplate jdbcTemplate;

    public TaskJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void save(AnalysisTask task) {
        jdbcTemplate.update(
                """
                INSERT INTO analysis_task (
                    task_id, project_id, repo_id, incident_id, task_type,
                    status, message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    project_id = VALUES(project_id),
                    repo_id = VALUES(repo_id),
                    incident_id = VALUES(incident_id),
                    task_type = VALUES(task_type),
                    status = VALUES(status),
                    message = VALUES(message),
                    updated_at = VALUES(updated_at)
                """,
                task.taskId(),
                task.projectId(),
                task.repoId(),
                task.incidentId(),
                task.type().name(),
                task.status().name(),
                task.message(),
                task.createdAt(),
                task.updatedAt()
        );
    }

    public Optional<AnalysisTask> findById(String taskId) {
        List<AnalysisTask> tasks = jdbcTemplate.query(
                """
                SELECT task_id, project_id, repo_id, incident_id, task_type,
                       status, message, created_at, updated_at
                FROM analysis_task
                WHERE task_id = ?
                """,
                this::mapRow,
                taskId
        );
        return tasks.stream().findFirst();
    }

    private AnalysisTask mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new AnalysisTask(
                rs.getString("task_id"),
                rs.getString("project_id"),
                rs.getString("repo_id"),
                rs.getString("incident_id"),
                AnalysisTaskType.valueOf(rs.getString("task_type")),
                AnalysisTaskStatus.valueOf(rs.getString("status")),
                rs.getString("message"),
                rs.getString("created_at"),
                rs.getString("updated_at")
        );
    }
}
