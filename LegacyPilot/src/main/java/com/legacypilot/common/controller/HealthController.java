package com.legacypilot.common.controller;

import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Minimal runtime health checks for infrastructure integration.
 */
@RestController
@RequestMapping("/api/health")
public class HealthController {
    private final JdbcTemplate jdbcTemplate;

    public HealthController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @GetMapping("/db")
    public Map<String, Object> database() {
        Integer result = jdbcTemplate.queryForObject("SELECT 1", Integer.class);
        return Map.of(
                "status", "UP",
                "database", "mysql",
                "result", result
        );
    }
}
