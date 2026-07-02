package com.legacypilot.onboarding.controller;

import com.legacypilot.onboarding.dto.OnboardProjectRequest;
import com.legacypilot.onboarding.dto.OnboardProjectResponse;
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
     * General project onboarding endpoint. Supports LOCAL_PATH now and reserves
     * GIT_URL for the public GitHub clone flow.
     */
    @PostMapping("/projects")
    public OnboardProjectResponse onboardProject(@RequestBody OnboardProjectRequest request) {
        return projectOnboardingService.onboardProject(request);
    }
}
