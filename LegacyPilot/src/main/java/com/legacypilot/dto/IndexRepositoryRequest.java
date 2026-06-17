package com.legacypilot.dto;

/**
 * Legacy request body for the placeholder /api/repos/index endpoint.
 *
 * This endpoint currently records repository metadata only. The newer
 * ConnectRepositoryRequest is the preferred path for local testing.
 */
public record IndexRepositoryRequest(
        /** Existing LegacyPilot project ID. */
        String projectId,
        /** Remote Git URL. Clone support is not implemented yet. */
        String repositoryUrl,
        /** Branch name requested for analysis. */
        String branch,
        /** Optional commit SHA requested for analysis. */
        String commitSha
) {
}
