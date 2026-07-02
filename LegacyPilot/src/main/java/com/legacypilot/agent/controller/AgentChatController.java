package com.legacypilot.agent.controller;

import com.legacypilot.agent.dto.chat.AgentChatRequest;
import com.legacypilot.agent.dto.chat.AgentChatResponse;
import com.legacypilot.agent.service.LegacyPilotAgent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Experimental chat entry point for the LegacyPilot agent skeleton.
 */
@RestController
@RequestMapping("/api/agent")
public class AgentChatController {
    private final LegacyPilotAgent legacyPilotAgent;

    public AgentChatController(LegacyPilotAgent legacyPilotAgent) {
        this.legacyPilotAgent = legacyPilotAgent;
    }

    @PostMapping("/chat")
    public AgentChatResponse chat(@RequestBody AgentChatRequest request) {
        return legacyPilotAgent.answer(request);
    }
}
