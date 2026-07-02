package com.legacypilot.onboarding.dto;

import com.legacypilot.project.entity.LegacyProject;
import com.legacypilot.repository.dto.RepositoryFilesResponse;
import com.legacypilot.repository.dto.RepositoryGraphAnalysisResponse;
import com.legacypilot.repository.entity.RepositoryIndex;

/**
 * Combined response for one project onboarding run.
 */
public record OnboardProjectResponse(
        LegacyProject project,
        RepositoryIndex repository,
        RepositoryFilesResponse files,
        RepositoryGraphAnalysisResponse graph
) {
}
