package com.legacypilot.agent.service;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * Temporary process-local agent context for the current demo workspace.
 *
 * This should become user/session/workspace scoped when authentication and
 * persistent workspaces are introduced.
 */
@Component
public class AgentContextStore {
    private final AtomicReference<String> currentRepoId = new AtomicReference<>();

    public void setCurrentRepoId(String repoId) {
        currentRepoId.set(repoId);
    }

    public String currentRepoId() {
        String repoId = currentRepoId.get();
        if (repoId == null || repoId.isBlank()) {
            throw new ResponseStatusException(NOT_FOUND, "No current repository is selected. Run onboarding first.");
        }
        return repoId;
    }
}
