package com.legacypilot.onboarding.controller;

import com.legacypilot.onboarding.dto.ConnectLocalProjectRequest;
import com.legacypilot.onboarding.dto.ConnectLocalProjectResponse;
import com.legacypilot.onboarding.service.ProjectOnboardingService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Project onboarding endpoints.
 */
@RestController
@RequestMapping("/api/onboarding")
public class OnboardingController {
    private final ProjectOnboardingService projectOnboardingService;

    public OnboardingController(ProjectOnboardingService projectOnboardingService) {
        this.projectOnboardingService = projectOnboardingService;
    }

    /**
     * One-shot local demo endpoint: create a project and connect a local Git
     * repository from one request so users do not need to copy projectId between
     * Postman calls.
     */
    @PostMapping("/local-project")
    public ConnectLocalProjectResponse connectLocalProject(@RequestBody ConnectLocalProjectRequest request) {
        return projectOnboardingService.connectLocalProject(request);
    }
}
