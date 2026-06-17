package com.legacypilot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Spring Boot application entry point for the Java backend.
 *
 * This service owns the product/control-plane side of LegacyPilot:
 * projects, repository connections, analysis tasks, incidents, and user
 * confirmation. AI/RAG and GitNexus integration will be connected behind these
 * APIs in later steps.
 */
@SpringBootApplication
public class LegacyPilotApplication {

    public static void main(String[] args) {
        SpringApplication.run(LegacyPilotApplication.class, args);
    }
}
