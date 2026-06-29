package com.legacypilot.lcms.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Request body expected by the LCMS Python code knowledge service.
 *
 * Java keeps camelCase names in code, while @JsonProperty emits the snake_case
 * contract used by FastAPI: /v1/repos/index.
 */
public record CodeKnowledgeIndexRequest(
        @JsonProperty("repo_id")
        String repoId,

        @JsonProperty("repo_uri")
        String repoUri,

        @JsonProperty("language_hint")
        String languageHint,

        @JsonProperty("parser_profile")
        String parserProfile,

        @JsonProperty("contract_version")
        String contractVersion
) {
}
