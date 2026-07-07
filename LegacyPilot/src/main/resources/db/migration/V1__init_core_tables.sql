CREATE TABLE legacy_project (
    project_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    repository_url VARCHAR(1024) NULL,
    default_branch VARCHAR(128) NOT NULL DEFAULT 'main',
    created_at VARCHAR(64) NOT NULL,
    PRIMARY KEY (project_id),
    KEY idx_legacy_project_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE repository_index (
    repo_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    repository_url VARCHAR(1024) NULL,
    local_repo_path VARCHAR(2048) NULL,
    branch_name VARCHAR(128) NULL,
    commit_sha VARCHAR(128) NULL,
    graph_id VARCHAR(128) NULL,
    task_id VARCHAR(64) NULL,
    created_at VARCHAR(64) NOT NULL,
    PRIMARY KEY (repo_id),
    KEY idx_repository_index_project_id (project_id),
    KEY idx_repository_index_task_id (task_id),
    KEY idx_repository_index_created_at (created_at),
    CONSTRAINT fk_repository_index_project
        FOREIGN KEY (project_id) REFERENCES legacy_project (project_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE analysis_task (
    task_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NULL,
    repo_id VARCHAR(64) NULL,
    incident_id VARCHAR(64) NULL,
    task_type VARCHAR(64) NOT NULL,
    status VARCHAR(64) NOT NULL,
    message TEXT NULL,
    created_at VARCHAR(64) NOT NULL,
    updated_at VARCHAR(64) NOT NULL,
    PRIMARY KEY (task_id),
    KEY idx_analysis_task_project_id (project_id),
    KEY idx_analysis_task_repo_id (repo_id),
    KEY idx_analysis_task_incident_id (incident_id),
    KEY idx_analysis_task_status (status),
    KEY idx_analysis_task_updated_at (updated_at),
    CONSTRAINT fk_analysis_task_project
        FOREIGN KEY (project_id) REFERENCES legacy_project (project_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_analysis_task_repository
        FOREIGN KEY (repo_id) REFERENCES repository_index (repo_id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE code_analysis_snapshot (
    snapshot_id BIGINT NOT NULL AUTO_INCREMENT,
    repo_id VARCHAR(64) NOT NULL,
    graph_id VARCHAR(128) NULL,
    project_type VARCHAR(64) NULL,
    node_count INT NOT NULL DEFAULT 0,
    edge_count INT NOT NULL DEFAULT 0,
    endpoint_count INT NOT NULL DEFAULT 0,
    class_count INT NOT NULL DEFAULT 0,
    method_count INT NOT NULL DEFAULT 0,
    result_json JSON NOT NULL,
    created_at VARCHAR(64) NOT NULL,
    PRIMARY KEY (snapshot_id),
    KEY idx_code_analysis_snapshot_repo_id (repo_id),
    KEY idx_code_analysis_snapshot_created_at (created_at),
    CONSTRAINT fk_code_analysis_snapshot_repository
        FOREIGN KEY (repo_id) REFERENCES repository_index (repo_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE incident_record (
    incident_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    repo_id VARCHAR(64) NULL,
    task_id VARCHAR(64) NULL,
    raw_log MEDIUMTEXT NULL,
    stack_trace MEDIUMTEXT NULL,
    error_description TEXT NULL,
    status VARCHAR(64) NOT NULL,
    confirmed_by_user BOOLEAN NOT NULL DEFAULT FALSE,
    fix_outcome TEXT NULL,
    retention_policy VARCHAR(128) NULL,
    created_at VARCHAR(64) NOT NULL,
    updated_at VARCHAR(64) NOT NULL,
    PRIMARY KEY (incident_id),
    KEY idx_incident_record_project_id (project_id),
    KEY idx_incident_record_repo_id (repo_id),
    KEY idx_incident_record_task_id (task_id),
    KEY idx_incident_record_status (status),
    KEY idx_incident_record_updated_at (updated_at),
    CONSTRAINT fk_incident_record_project
        FOREIGN KEY (project_id) REFERENCES legacy_project (project_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_incident_record_repository
        FOREIGN KEY (repo_id) REFERENCES repository_index (repo_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_incident_record_task
        FOREIGN KEY (task_id) REFERENCES analysis_task (task_id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
