package com.legacypilot.dto;

import com.legacypilot.entity.LegacyProject;
import com.legacypilot.entity.RepositoryIndex;

/**
 * Combined response for the one-shot local project connection flow.
 */
public record ConnectLocalProjectResponse(
        /** Newly created project metadata. */
        LegacyProject project,
        /** Newly connected repository metadata. */
        RepositoryIndex repository
) {
}
