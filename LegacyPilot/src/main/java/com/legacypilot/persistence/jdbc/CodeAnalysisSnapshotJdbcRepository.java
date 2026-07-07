package com.legacypilot.persistence.jdbc;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.legacypilot.codeanalysis.entity.CodeAnalysisResult;
import com.legacypilot.codeanalysis.entity.CodeGraphSummary;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CodeAnalysisSnapshotJdbcRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public CodeAnalysisSnapshotJdbcRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public void insert(String repoId, CodeAnalysisResult result) {
        CodeGraphSummary summary = result.summary();
        deleteByRepoId(repoId);
        jdbcTemplate.update(
                """
                INSERT INTO code_analysis_snapshot (
                    repo_id, graph_id, project_type, node_count, edge_count,
                    endpoint_count, class_count, method_count, result_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                repoId,
                "GRAPH-" + repoId,
                summary.projectType(),
                summary.nodeCount(),
                summary.edgeCount(),
                summary.endpointCount(),
                summary.classCount(),
                summary.methodCount(),
                toJson(result),
                Instant.now().toString()
        );
    }

    public void deleteByRepoId(String repoId) {
        jdbcTemplate.update(
                "DELETE FROM code_analysis_snapshot WHERE repo_id = ?",
                repoId
        );
    }

    public Optional<CodeAnalysisResult> findLatestByRepoId(String repoId) {
        List<CodeAnalysisResult> results = jdbcTemplate.query(
                """
                SELECT result_json
                FROM code_analysis_snapshot
                WHERE repo_id = ?
                ORDER BY snapshot_id DESC
                LIMIT 1
                """,
                this::mapResult,
                repoId
        );
        return results.stream().findFirst();
    }

    private CodeAnalysisResult mapResult(ResultSet rs, int rowNum) throws SQLException {
        try {
            return objectMapper.readValue(rs.getString("result_json"), CodeAnalysisResult.class);
        } catch (JsonProcessingException exception) {
            throw new SQLException("Failed to parse code analysis snapshot JSON.", exception);
        }
    }

    private String toJson(CodeAnalysisResult result) {
        try {
            return objectMapper.writeValueAsString(result);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Failed to serialize code analysis result.", exception);
        }
    }
}
