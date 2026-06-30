import type { AlertEvent, RepoIndexRequest, SaveIncidentRequest } from "./contracts";

export const contractVersion = "1.0.0";

export function defaultRepoRequest(): RepoIndexRequest {
  return {
    repo_id: "",
    repo_uri: "",
    language_hint: "java",
    parser_profile: "spring-boot",
    contract_version: contractVersion,
  };
}

export function defaultAlert(repoId = ""): AlertEvent {
  return {
    alert_id: "",
    repo_id: repoId,
    graph_id: "",
    raw_log: "",
    stack_trace: "",
    error_description: "",
    occurred_at: new Date().toISOString(),
    source: "frontend-workbench",
    contract_version: contractVersion,
  };
}

export function defaultSaveRequest(): Pick<
  SaveIncidentRequest,
  "user_confirmation" | "fix_outcome" | "retention_policy" | "contract_version"
> {
  return {
    user_confirmation: false,
    fix_outcome: "",
    retention_policy: "",
    contract_version: contractVersion,
  };
}
