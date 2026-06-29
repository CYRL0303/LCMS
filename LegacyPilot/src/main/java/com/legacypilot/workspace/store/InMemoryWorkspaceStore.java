package com.legacypilot.workspace.store;

import com.legacypilot.incident.entity.IncidentRecord;
import com.legacypilot.project.entity.LegacyProject;
import com.legacypilot.repository.entity.RepositoryIndex;
import com.legacypilot.task.entity.AnalysisTask;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * Temporary process-local storage until database persistence is introduced.
 */
@Component
public class InMemoryWorkspaceStore {
    private final Map<String, LegacyProject> projects = new ConcurrentHashMap<>();
    private final Map<String, RepositoryIndex> repositories = new ConcurrentHashMap<>();
    private final Map<String, AnalysisTask> tasks = new ConcurrentHashMap<>();
    private final Map<String, IncidentRecord> incidents = new ConcurrentHashMap<>();

    public Map<String, LegacyProject> projects() {
        return projects;
    }

    public Map<String, RepositoryIndex> repositories() {
        return repositories;
    }

    public Map<String, AnalysisTask> tasks() {
        return tasks;
    }

    public Map<String, IncidentRecord> incidents() {
        return incidents;
    }
}
