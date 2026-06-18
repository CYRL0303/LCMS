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
        RepositoryIndex repository,
        /** Immediate file scan result for the connected local repository. */
        RepositoryFilesResponse files,
        /** Code graph analysis summary returned by the Python code knowledge service. */
        RepositoryGraphAnalysisResponse graph
) {
}
