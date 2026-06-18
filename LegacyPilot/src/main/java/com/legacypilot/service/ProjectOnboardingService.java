package com.legacypilot.service;

import com.legacypilot.dto.ConnectLocalProjectRequest;
import com.legacypilot.dto.ConnectLocalProjectResponse;
import com.legacypilot.dto.RepositoryGraphAnalysisResponse;
import org.springframework.stereotype.Service;

/**
 * Coordinates the full one-shot local project onboarding workflow.
 *
 * The lower-level AnalysisService still owns project/repository creation and
 * file scanning. This service adds the code graph analysis step so the main
 * frontend flow can stay one API call.
 */
@Service
public class ProjectOnboardingService {
    private final AnalysisService analysisService;
    private final RepositoryCodeAnalysisService repositoryCodeAnalysisService;

    public ProjectOnboardingService(
            AnalysisService analysisService,
            RepositoryCodeAnalysisService repositoryCodeAnalysisService
    ) {
        this.analysisService = analysisService;
        this.repositoryCodeAnalysisService = repositoryCodeAnalysisService;
    }

    /**
     * Creates the project/repository, scans files, then indexes the repository
     * through the Python code knowledge service.
     */
    public ConnectLocalProjectResponse connectLocalProject(ConnectLocalProjectRequest request) {
        ConnectLocalProjectResponse connected = analysisService.connectLocalProject(request);
        RepositoryGraphAnalysisResponse graph =
                repositoryCodeAnalysisService.analyzeRepository(connected.repository().repoId());

        return new ConnectLocalProjectResponse(
                connected.project(),
                connected.repository(),
                connected.files(),
                graph
        );
    }
}
