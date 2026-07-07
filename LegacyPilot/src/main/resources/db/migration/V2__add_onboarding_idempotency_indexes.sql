ALTER TABLE legacy_project
    ADD COLUMN owner_id VARCHAR(64) NOT NULL DEFAULT 'local-dev' AFTER project_id,
    ADD UNIQUE KEY uk_legacy_project_owner_name (owner_id, name);

ALTER TABLE repository_index
    ADD KEY idx_repository_index_source_lookup (
        project_id,
        source_type,
        local_repo_path(191),
        repository_url(191),
        branch_name,
        commit_sha
    );
