import {
  Activity,
  AlertTriangle,
  Archive,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  Database,
  GitBranch,
  Loader2,
  Play,
  RotateCcw,
  Save,
  Server,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  ApiRequestError,
  apiBase,
  getJson,
  isContractError,
  postJson,
} from "./api";
import {
  defaultAlert,
  defaultRepoRequest,
  defaultSaveRequest,
} from "./defaults";
import type {
  AlertEvent,
  ContractError,
  EvidenceBackedItem,
  EvidenceBundle,
  EvidenceRef,
  GenericApiError,
  GraphSnapshot,
  HealthResponse,
  IncidentQuery,
  IncidentRecord,
  RCAReport,
  RepoIndexRequest,
  ReviewedRCAReport,
  SaveIncidentRequest,
  StepKey,
  StepLog,
  StepStatus,
} from "./contracts";

const stepMeta: Record<StepKey, { label: string; endpoint: string; icon: LucideIcon }> = {
  health: { label: "Health", endpoint: "GET /health", icon: Server },
  index: { label: "IndexRepo", endpoint: "POST /v1/repos/index", icon: GitBranch },
  submit: { label: "SubmitAlert", endpoint: "POST /v1/alerts/submit", icon: Activity },
  evidence: {
    label: "BuildEvidenceBundle",
    endpoint: "POST /v1/evidence-bundles/build",
    icon: Database,
  },
  generate: { label: "GenerateRCA", endpoint: "POST /v1/rca/generate", icon: BrainCircuit },
  review: { label: "ReviewRCA", endpoint: "POST /v1/rca/review", icon: ShieldCheck },
  save: { label: "SaveIncident", endpoint: "POST /v1/incidents/save", icon: Archive },
  readback: { label: "ReadIncident", endpoint: "GET /v1/incidents/{incident_id}", icon: Database },
};

const stepOrder: StepKey[] = [
  "health",
  "index",
  "submit",
  "evidence",
  "generate",
  "review",
  "save",
  "readback",
];

type StepLogs = Record<StepKey, StepLog>;

function initialStepLogs(): StepLogs {
  return stepOrder.reduce((logs, key) => {
    logs[key] = {
      key,
      label: stepMeta[key].label,
      status: "idle",
      endpoint: stepMeta[key].endpoint,
    };
    return logs;
  }, {} as StepLogs);
}

export function App() {
  const [repoRequest, setRepoRequest] = useState<RepoIndexRequest>(defaultRepoRequest);
  const [alertEvent, setAlertEvent] = useState<AlertEvent>(() =>
    defaultAlert(defaultRepoRequest().repo_id),
  );
  const [saveDraft, setSaveDraft] = useState(defaultSaveRequest);
  const [stepLogs, setStepLogs] = useState<StepLogs>(initialStepLogs);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [snapshot, setSnapshot] = useState<GraphSnapshot | null>(null);
  const [incidentQuery, setIncidentQuery] = useState<IncidentQuery | null>(null);
  const [bundle, setBundle] = useState<EvidenceBundle | null>(null);
  const [rcaReport, setRcaReport] = useState<RCAReport | null>(null);
  const [reviewedReport, setReviewedReport] = useState<ReviewedRCAReport | null>(null);
  const [incidentRecord, setIncidentRecord] = useState<IncidentRecord | null>(null);
  const [persistedIncidentRecord, setPersistedIncidentRecord] = useState<IncidentRecord | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);

  useEffect(() => {
    void runHealth();
  }, []);

  const latestTraceId =
    incidentRecord?.incident_id && reviewedReport?.trace_id
      ? reviewedReport.trace_id
      : reviewedReport?.trace_id ||
        rcaReport?.trace_id ||
        bundle?.trace_id ||
        incidentQuery?.trace_id ||
        null;

  const canUseApi = stepLogs.health.status === "passed";
  const canIndex = canUseApi && Boolean(repoRequest.repo_id.trim() && repoRequest.repo_uri.trim());
  const canSubmit = canUseApi && Boolean(alertEvent.alert_id.trim() && alertEvent.repo_id.trim());
  const canBuildEvidence = canUseApi && incidentQuery !== null;
  const canGenerateRca = canUseApi && bundle !== null;
  const canReviewRca = canUseApi && rcaReport !== null;
  const canSave =
    canUseApi &&
    reviewedReport !== null &&
    saveDraft.user_confirmation &&
    saveDraft.fix_outcome.trim().length > 0 &&
    saveDraft.retention_policy.trim().length > 0;

  async function runHealth(): Promise<HealthResponse | null> {
    return runStep<HealthResponse>(
      "health",
      undefined,
      () => getJson<HealthResponse>("/health"),
      (data) => setHealth(data),
    );
  }

  async function runIndex(): Promise<GraphSnapshot | null> {
    const request = normalizeRepoRequest(repoRequest);
    return runStep<GraphSnapshot>(
      "index",
      request,
      () => postJson<GraphSnapshot>("/v1/repos/index", request),
      (data) => {
        setSnapshot(data);
        setAlertEvent((current) => ({
          ...current,
          repo_id: data.repo_id,
          graph_id: data.graph_id,
        }));
      },
    );
  }

  function skipIndex() {
    setSnapshot(null);
    updateStep("index", {
      status: "skipped",
      request: null,
      response: {
        graph_id: alertEvent.graph_id || null,
        note: "Using graph_id from AlertEvent.",
      },
      error: undefined,
      httpStatus: undefined,
      elapsedMs: undefined,
    });
    clearPipelineAfter("index");
  }

  async function runSubmitAlert(override?: Partial<AlertEvent>): Promise<IncidentQuery | null> {
    const request = normalizeAlertEvent({ ...alertEvent, ...override });
    return runStep<IncidentQuery>(
      "submit",
      request,
      () => postJson<IncidentQuery>("/v1/alerts/submit", request),
      (data) => {
        setIncidentQuery(data);
        setAlertEvent((current) => ({
          ...current,
          repo_id: data.repo_id,
          graph_id: data.graph_id || current.graph_id,
        }));
      },
    );
  }

  async function runBuildEvidence(
    input: IncidentQuery | null = incidentQuery,
  ): Promise<EvidenceBundle | null> {
    if (!input) {
      return null;
    }
    return runStep<EvidenceBundle>(
      "evidence",
      input,
      () => postJson<EvidenceBundle>("/v1/evidence-bundles/build", input),
      (data) => setBundle(data),
    );
  }

  async function runGenerateRca(input: EvidenceBundle | null = bundle): Promise<RCAReport | null> {
    if (!input) {
      return null;
    }
    return runStep<RCAReport>(
      "generate",
      input,
      () => postJson<RCAReport>("/v1/rca/generate", input),
      (data) => setRcaReport(data),
    );
  }

  async function runReviewRca(input: RCAReport | null = rcaReport): Promise<ReviewedRCAReport | null> {
    if (!input) {
      return null;
    }
    return runStep<ReviewedRCAReport>(
      "review",
      input,
      () => postJson<ReviewedRCAReport>("/v1/rca/review", input),
      (data) => setReviewedReport(data),
    );
  }

  async function runSaveIncident(
    input: ReviewedRCAReport | null = reviewedReport,
  ): Promise<IncidentRecord | null> {
    if (!input) {
      return null;
    }
    const request: SaveIncidentRequest = {
      reviewed_report: input,
      user_confirmation: saveDraft.user_confirmation,
      fix_outcome: saveDraft.fix_outcome,
      retention_policy: saveDraft.retention_policy,
      contract_version: saveDraft.contract_version,
    };
    return runStep<IncidentRecord>(
      "save",
      request,
      () => postJson<IncidentRecord>("/v1/incidents/save", request),
      (data) => setIncidentRecord(data),
    ).then(async (record) => {
      if (record) {
        await runLoadIncident(record.incident_id);
      }
      return record;
    });
  }

  async function runLoadIncident(incidentId: string): Promise<IncidentRecord | null> {
    return runStep<IncidentRecord>(
      "readback",
      { incident_id: incidentId },
      () => getJson<IncidentRecord>(`/v1/incidents/${encodeURIComponent(incidentId)}`),
      (data) => setPersistedIncidentRecord(data),
    );
  }

  async function runFullPipeline() {
    let nextSnapshot = snapshot;
    if (!nextSnapshot && repoRequest.repo_uri.trim()) {
      nextSnapshot = await runIndex();
      if (!nextSnapshot) {
        return;
      }
    }

    const nextQuery = await runSubmitAlert({
      repo_id: nextSnapshot?.repo_id || alertEvent.repo_id,
      graph_id: nextSnapshot?.graph_id || alertEvent.graph_id || undefined,
    });
    if (!nextQuery) {
      return;
    }

    const nextBundle = await runBuildEvidence(nextQuery);
    if (!nextBundle) {
      return;
    }

    const nextReport = await runGenerateRca(nextBundle);
    if (!nextReport) {
      return;
    }

    await runReviewRca(nextReport);
  }

  async function runStep<T>(
    key: StepKey,
    request: unknown,
    call: () => Promise<{ data: T; httpStatus: number; elapsedMs: number }>,
    onSuccess: (data: T) => void,
  ): Promise<T | null> {
    updateStep(key, {
      status: "running",
      request,
      response: undefined,
      error: undefined,
      httpStatus: undefined,
      elapsedMs: undefined,
    });
    try {
      const result = await call();
      onSuccess(result.data);
      updateStep(key, {
        status: "passed",
        request,
        response: result.data,
        httpStatus: result.httpStatus,
        elapsedMs: result.elapsedMs,
        error: undefined,
      });
      return result.data;
    } catch (error) {
      const { httpStatus, body } = unpackError(error);
      updateStep(key, {
        status: "failed",
        request,
        response: undefined,
        error: body,
        httpStatus,
        elapsedMs: undefined,
      });
      setDebugOpen(true);
      return null;
    }
  }

  function updateStep(key: StepKey, patch: Partial<StepLog>) {
    setStepLogs((current) => ({
      ...current,
      [key]: {
        ...current[key],
        ...patch,
      },
    }));
  }

  function resetAll() {
    setStepLogs(initialStepLogs());
    setHealth(null);
    setSnapshot(null);
    setIncidentQuery(null);
    setBundle(null);
    setRcaReport(null);
    setReviewedReport(null);
    setIncidentRecord(null);
    setPersistedIncidentRecord(null);
    void runHealth();
  }

  function clearPipelineAfter(key: StepKey) {
    const start = stepOrder.indexOf(key) + 1;
    const keys = stepOrder.slice(start);
    setStepLogs((current) => {
      const next = { ...current };
      for (const downstream of keys) {
        next[downstream] = {
          ...next[downstream],
          status: "idle",
          request: undefined,
          response: undefined,
          error: undefined,
          httpStatus: undefined,
          elapsedMs: undefined,
        };
      }
      return next;
    });
    if (keys.includes("submit")) {
      setIncidentQuery(null);
    }
    if (keys.includes("evidence")) {
      setBundle(null);
    }
    if (keys.includes("generate")) {
      setRcaReport(null);
    }
    if (keys.includes("review")) {
      setReviewedReport(null);
    }
    if (keys.includes("save")) {
      setIncidentRecord(null);
    }
    if (keys.includes("readback")) {
      setPersistedIncidentRecord(null);
    }
  }

  function setRepoField(field: keyof RepoIndexRequest, value: string) {
    setRepoRequest((current) => {
      const next = { ...current, [field]: value };
      if (field === "repo_id") {
        setAlertEvent((alert) => ({ ...alert, repo_id: value }));
      }
      return next;
    });
    clearPipelineAfter("health");
    setSnapshot(null);
  }

  function setAlertField(field: keyof AlertEvent, value: string) {
    setAlertEvent((current) => ({ ...current, [field]: value }));
    clearPipelineAfter("index");
  }

  const runMode = useMemo(() => {
    if (stepLogs.health.status !== "passed") {
      return "unknown";
    }
    return apiBase.startsWith("/api") ? "proxied real backend" : "configured backend";
  }, [stepLogs.health.status]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">LegacyPilot</p>
          <h1>Incident Workbench</h1>
        </div>
        <div className="topbar-actions">
          <button className="icon-button secondary" onClick={() => void runHealth()}>
            <Server aria-hidden="true" />
            Health
          </button>
          <button className="icon-button secondary" onClick={resetAll}>
            <RotateCcw aria-hidden="true" />
            Reset
          </button>
          <button
            className="icon-button primary"
            data-testid="run-full-pipeline"
            disabled={!canUseApi || (!repoRequest.repo_uri.trim() && !alertEvent.graph_id)}
            onClick={() => void runFullPipeline()}
          >
            <Play aria-hidden="true" />
            Run full pipeline
          </button>
        </div>
      </header>

      <StatusBar
        health={health}
        healthStatus={stepLogs.health.status}
        latestTraceId={latestTraceId}
        runMode={runMode}
      />

      <PipelineStepper logs={stepLogs} />

      <div className="workspace-grid">
        <section className="panel controls-panel" aria-labelledby="inputs-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Inputs</p>
              <h2 id="inputs-heading">Source and Alert</h2>
            </div>
          </div>
          <RepoIndexForm
            value={repoRequest}
            canIndex={canIndex}
            onChange={setRepoField}
            onIndex={() => void runIndex()}
            onSkip={skipIndex}
          />
          <AlertForm
            value={alertEvent}
            canSubmit={canSubmit}
            onChange={setAlertField}
            onSubmit={() => void runSubmitAlert()}
          />
          <SaveForm
            value={saveDraft}
            canSave={canSave}
            onChange={setSaveDraft}
            onSave={() => void runSaveIncident()}
          />
        </section>

        <section className="panel flow-panel" aria-labelledby="flow-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Four structures</p>
              <h2 id="flow-heading">Pipeline Output</h2>
            </div>
            <button
              className="icon-button secondary"
              disabled={!canBuildEvidence}
              onClick={() => void runBuildEvidence()}
            >
              <Database aria-hidden="true" />
              Build evidence
            </button>
          </div>
          <SnapshotSummary snapshot={snapshot} />
          <IncidentQuerySummary query={incidentQuery} />
          <EvidenceBundleView bundle={bundle} />
          <div className="inline-actions">
            <button
              className="icon-button secondary"
              disabled={!canGenerateRca}
              onClick={() => void runGenerateRca()}
            >
              <BrainCircuit aria-hidden="true" />
              Generate RCA
            </button>
            <button
              className="icon-button secondary"
              disabled={!canReviewRca}
              onClick={() => void runReviewRca()}
            >
              <ShieldCheck aria-hidden="true" />
              Review RCA
            </button>
          </div>
        </section>

        <section className="panel result-panel" aria-labelledby="results-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Reasoning and Memory</p>
              <h2 id="results-heading">RCA Result</h2>
            </div>
            <button
              className="icon-button secondary"
              onClick={() => setDebugOpen((open) => !open)}
            >
              <ClipboardList aria-hidden="true" />
              Contract debug
            </button>
          </div>
          <RCAReportView report={rcaReport} />
          <ReviewedReportView report={reviewedReport} />
          <IncidentRecordView record={incidentRecord} />
          <IncidentReadbackView record={persistedIncidentRecord} />
        </section>
      </div>

      <ContractDebugDrawer
        open={debugOpen}
        logs={stepLogs}
        onClose={() => setDebugOpen(false)}
      />
    </main>
  );
}

function StatusBar({
  health,
  healthStatus,
  latestTraceId,
  runMode,
}: {
  health: HealthResponse | null;
  healthStatus: StepStatus;
  latestTraceId: string | null;
  runMode: string;
}) {
  return (
    <section className="statusbar" aria-label="Backend status">
      <StatusBadge status={healthStatus} />
      <span className="status-item">
        API <strong>{apiBase}</strong>
      </span>
      <span className="status-item">
        Service <strong>{health?.service || "unavailable"}</strong>
      </span>
      <span className="status-item">
        Contract <strong>{health?.contract_version || "unknown"}</strong>
      </span>
      <span className="status-item">
        Mode <strong>{runMode}</strong>
      </span>
      {Object.entries(health?.backends || {}).map(([name, backend]) => (
        <span className="status-item" key={name}>
          {backendLabel(name)} <strong>{backend}</strong>
        </span>
      ))}
      <span className="status-item">
        Trace <strong data-testid="latest-trace-id">{latestTraceId || "none"}</strong>
      </span>
    </section>
  );
}

function backendLabel(name: string): string {
  const labels: Record<string, string> = {
    code_knowledge_core: "S1",
    incident_context_builder: "S2",
    rca_reasoning_engine: "S3",
    incident_memory_store: "S4",
  };
  return labels[name] || name;
}

function PipelineStepper({ logs }: { logs: StepLogs }) {
  return (
    <section className="stepper" aria-label="Pipeline status">
      {stepOrder.map((key) => {
        const log = logs[key];
        const Icon = stepMeta[key].icon;
        return (
          <div className={`step step-${log.status}`} key={key} data-testid={`step-${key}`}>
            <Icon aria-hidden="true" />
            <div>
              <span>{log.label}</span>
              <small>{formatStepDetail(log)}</small>
            </div>
          </div>
        );
      })}
    </section>
  );
}

function RepoIndexForm({
  value,
  canIndex,
  onChange,
  onIndex,
  onSkip,
}: {
  value: RepoIndexRequest;
  canIndex: boolean;
  onChange: (field: keyof RepoIndexRequest, value: string) => void;
  onIndex: () => void;
  onSkip: () => void;
}) {
  return (
    <div className="form-block">
      <div className="block-title">
        <GitBranch aria-hidden="true" />
        <h3>Structure1 Repo Index</h3>
      </div>
      <label>
        Repo ID
        <input
          value={value.repo_id}
          onChange={(event) => onChange("repo_id", event.target.value)}
        />
      </label>
      <label>
        Repo URI
        <input
          data-testid="repo-uri-input"
          placeholder="file:///absolute/path/to/repo or https://github.com/owner/repo"
          value={value.repo_uri}
          onChange={(event) => onChange("repo_uri", event.target.value)}
        />
      </label>
      <div className="two-col">
        <label>
          Language
          <input
            value={value.language_hint}
            onChange={(event) => onChange("language_hint", event.target.value)}
          />
        </label>
        <label>
          Parser profile
          <input
            value={value.parser_profile}
            onChange={(event) => onChange("parser_profile", event.target.value)}
          />
        </label>
      </div>
      <label>
        Contract version
        <input
          value={value.contract_version}
          onChange={(event) => onChange("contract_version", event.target.value)}
        />
      </label>
      <div className="inline-actions">
        <button className="icon-button secondary" disabled={!canIndex} onClick={onIndex}>
          <Database aria-hidden="true" />
          Index repo
        </button>
        <button className="icon-button ghost" onClick={onSkip}>
          <Play aria-hidden="true" />
          Use existing graph
        </button>
      </div>
    </div>
  );
}

function AlertForm({
  value,
  canSubmit,
  onChange,
  onSubmit,
}: {
  value: AlertEvent;
  canSubmit: boolean;
  onChange: (field: keyof AlertEvent, value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <div className="form-block">
      <div className="block-title">
        <Activity aria-hidden="true" />
        <h3>Structure2 Alert</h3>
      </div>
      <div className="two-col">
        <label>
          Alert ID
          <input
            data-testid="alert-id-input"
            value={value.alert_id}
            onChange={(event) => onChange("alert_id", event.target.value)}
          />
        </label>
        <label>
          Source
          <input value={value.source} onChange={(event) => onChange("source", event.target.value)} />
        </label>
      </div>
      <label>
        Graph ID
        <input
          data-testid="graph-id-input"
          value={value.graph_id || ""}
          onChange={(event) => onChange("graph_id", event.target.value)}
        />
      </label>
      <label>
        Raw log
        <textarea
          data-testid="raw-log-input"
          rows={5}
          value={value.raw_log}
          onChange={(event) => onChange("raw_log", event.target.value)}
        />
      </label>
      <label>
        Stack trace
        <textarea
          rows={3}
          value={value.stack_trace || ""}
          onChange={(event) => onChange("stack_trace", event.target.value)}
        />
      </label>
      <label>
        Error description
        <input
          value={value.error_description || ""}
          onChange={(event) => onChange("error_description", event.target.value)}
        />
      </label>
      <div className="two-col">
        <label>
          Occurred at
          <input
            value={value.occurred_at}
            onChange={(event) => onChange("occurred_at", event.target.value)}
          />
        </label>
        <label>
          Contract version
          <input
            value={value.contract_version}
            onChange={(event) => onChange("contract_version", event.target.value)}
          />
        </label>
      </div>
      <button className="icon-button secondary" disabled={!canSubmit} onClick={onSubmit}>
        <Activity aria-hidden="true" />
        Submit alert
      </button>
    </div>
  );
}

function SaveForm({
  value,
  canSave,
  onChange,
  onSave,
}: {
  value: ReturnType<typeof defaultSaveRequest>;
  canSave: boolean;
  onChange: (value: ReturnType<typeof defaultSaveRequest>) => void;
  onSave: () => void;
}) {
  return (
    <div className="form-block">
      <div className="block-title">
        <Archive aria-hidden="true" />
        <h3>Structure4 Save</h3>
      </div>
      <label className="check-row">
        <input
          data-testid="user-confirmation-checkbox"
          type="checkbox"
          checked={value.user_confirmation}
          onChange={(event) =>
            onChange({ ...value, user_confirmation: event.target.checked })
          }
        />
        User confirmed reviewed RCA
      </label>
      <label>
        Fix outcome
        <textarea
          rows={3}
          value={value.fix_outcome}
          onChange={(event) => onChange({ ...value, fix_outcome: event.target.value })}
        />
      </label>
      <div className="two-col">
        <label>
          Retention policy
          <input
            value={value.retention_policy}
            onChange={(event) => onChange({ ...value, retention_policy: event.target.value })}
          />
        </label>
        <label>
          Contract version
          <input
            value={value.contract_version}
            onChange={(event) => onChange({ ...value, contract_version: event.target.value })}
          />
        </label>
      </div>
      <button
        className="icon-button primary"
        data-testid="save-incident-button"
        disabled={!canSave}
        onClick={onSave}
      >
        <Save aria-hidden="true" />
        Save incident
      </button>
    </div>
  );
}

function SnapshotSummary({ snapshot }: { snapshot: GraphSnapshot | null }) {
  if (!snapshot) {
    return <EmptyState title="No GraphSnapshot yet" detail="Index repo or use existing graph_id." />;
  }
  return (
    <div className="summary-block" data-testid="snapshot-summary">
      <h3>GraphSnapshot</h3>
      <div className="metric-grid">
        <Metric label="graph_id" value={snapshot.graph_id} />
        <Metric label="nodes" value={snapshot.nodes.length.toString()} />
        <Metric label="edges" value={snapshot.edges.length.toString()} />
        <Metric label="evidence" value={snapshot.evidence_refs.length.toString()} />
      </div>
      <p className="meta-line">Parser: {snapshot.parser_version || "unknown"}</p>
      <p className="meta-line">
        Semantic: {snapshot.semantic_enrichment_version || "not reported"}
      </p>
    </div>
  );
}

function IncidentQuerySummary({ query }: { query: IncidentQuery | null }) {
  if (!query) {
    return <EmptyState title="No IncidentQuery yet" detail="Submit alert to extract trace and query terms." />;
  }
  return (
    <div className="summary-block" data-testid="incident-query-summary">
      <h3>IncidentQuery</h3>
      <div className="metric-grid">
        <Metric label="trace_id" value={query.trace_id} />
        <Metric label="error_type" value={query.error_type} />
        <Metric label="graph_id" value={query.graph_id || "none"} />
        <Metric label="endpoint" value={query.endpoint || "none"} />
      </div>
      <TagList title="Query terms" values={query.query_terms} />
    </div>
  );
}

function EvidenceBundleView({ bundle }: { bundle: EvidenceBundle | null }) {
  if (!bundle) {
    return <EmptyState title="No EvidenceBundle yet" detail="Build evidence after SubmitAlert." />;
  }
  return (
    <div className="summary-block" data-testid="evidence-bundle">
      <h3>EvidenceBundle</h3>
      <p className="summary-text">{bundle.alert_summary}</p>
      <div className="metric-grid">
        <Metric label="matched nodes" value={bundle.matched_nodes.length.toString()} />
        <Metric label="graph paths" value={bundle.graph_paths.length.toString()} />
        <Metric label="similar incidents" value={bundle.similar_incidents.length.toString()} />
        <Metric label="missing evidence" value={bundle.missing_evidence.length.toString()} />
      </div>
      <PathList paths={bundle.graph_paths} />
      <SimilarIncidentList incidents={bundle.similar_incidents} />
      <EvidenceGroup title="Code evidence" evidence={bundle.code_evidence} />
      <EvidenceGroup title="SQL evidence" evidence={bundle.sql_evidence} />
      <EvidenceGroup title="Config evidence" evidence={bundle.config_evidence} />
      <EvidenceGroup title="Log evidence" evidence={bundle.log_evidence} />
      {bundle.missing_evidence.length > 0 && (
        <div className="warning-box">
          <AlertTriangle aria-hidden="true" />
          <span>{bundle.missing_evidence.join(", ")}</span>
        </div>
      )}
    </div>
  );
}

function SimilarIncidentList({ incidents }: { incidents: EvidenceBundle["similar_incidents"] }) {
  if (incidents.length === 0) {
    return <TagList title="Similar incidents" values={[]} />;
  }
  return (
    <div className="finding-list" data-testid="similar-incident-list">
      <h4>Similar incidents</h4>
      {incidents.map((incident) => (
        <div className="finding-card" key={incident.incident_id}>
          <p>
            <strong>{incident.incident_id}</strong> {confidence(incident.similarity)}
          </p>
          <p>{incident.previous_root_cause}</p>
          <small>{incident.previous_fix}</small>
        </div>
      ))}
    </div>
  );
}

function RCAReportView({ report }: { report: RCAReport | null }) {
  if (!report) {
    return <EmptyState title="No RCAReport yet" detail="Generate RCA from evidence bundle." />;
  }
  return (
    <div className="summary-block" data-testid="rca-report">
      <h3>RCAReport</h3>
      <div className="metric-grid">
        <Metric label="report_id" value={report.report_id} />
        <Metric label="confidence" value={confidence(report.confidence)} />
        <Metric label="evidence chain" value={report.evidence_chain.length.toString()} />
        <Metric label="open questions" value={report.open_questions.length.toString()} />
      </div>
      <EvidenceBackedCard title="Selected root cause" item={report.selected_root_cause} />
      <EvidenceBackedList title="Hypotheses" items={report.hypotheses} />
      <EvidenceBackedList title="Suggested fix" items={report.suggested_fix} />
      <EvidenceBackedCard title="Migration impact" item={report.migration_impact} />
      <TagList title="Migration checklist" values={report.migration_checklist} />
    </div>
  );
}

function ReviewedReportView({ report }: { report: ReviewedRCAReport | null }) {
  if (!report) {
    return <EmptyState title="No ReviewedRCAReport yet" detail="Review RCA to approve evidence-backed findings." />;
  }
  return (
    <div className="summary-block" data-testid="reviewed-report">
      <h3>ReviewedRCAReport</h3>
      <div className="metric-grid">
        <Metric label="report_id" value={report.report_id} />
        <Metric label="final confidence" value={confidence(report.final_confidence)} />
        <Metric label="approved" value={report.approved_findings.length.toString()} />
        <Metric label="rejected" value={report.rejected_findings.length.toString()} />
      </div>
      <EvidenceBackedList title="Approved findings" items={report.approved_findings} />
      <TagList title="Risk notes" values={report.risk_notes} />
      <TagList title="Missing evidence" values={report.missing_evidence} />
    </div>
  );
}

function IncidentRecordView({ record }: { record: IncidentRecord | null }) {
  if (!record) {
    return <EmptyState title="No IncidentRecord yet" detail="Confirm reviewed RCA, then save incident." />;
  }
  return (
    <div className="summary-block success-block" data-testid="incident-record">
      <h3>IncidentRecord</h3>
      <div className="metric-grid">
        <Metric label="incident_id" value={record.incident_id} />
        <Metric label="dedup_key" value={record.dedup_key} />
        <Metric label="confirmed" value={record.confirmed_by_user ? "true" : "false"} />
        <Metric label="evidence" value={record.evidence_refs.length.toString()} />
      </div>
      <p className="summary-text">
        <strong>Root cause:</strong> {record.root_cause}
      </p>
      <p className="summary-text">
        <strong>Fix:</strong> {record.fix}
      </p>
      <EvidenceGroup title="Incident evidence" evidence={record.evidence_refs} />
    </div>
  );
}

function IncidentReadbackView({ record }: { record: IncidentRecord | null }) {
  if (!record) {
    return <EmptyState title="No persisted readback yet" detail="Saved incidents are read back through Structure4." />;
  }
  return (
    <div className="summary-block success-block" data-testid="incident-readback">
      <h3>Persisted readback</h3>
      <div className="metric-grid">
        <Metric label="incident_id" value={record.incident_id} />
        <Metric label="dedup_key" value={record.dedup_key} />
        <Metric label="updated" value={new Date(record.updated_at).toLocaleString()} />
        <Metric label="evidence" value={record.evidence_refs.length.toString()} />
      </div>
      <p className="summary-text">
        <strong>Root cause:</strong> {record.root_cause}
      </p>
      <p className="summary-text">
        <strong>Fix:</strong> {record.fix}
      </p>
    </div>
  );
}

function ContractDebugDrawer({
  open,
  logs,
  onClose,
}: {
  open: boolean;
  logs: StepLogs;
  onClose: () => void;
}) {
  if (!open) {
    return null;
  }
  return (
    <aside className="debug-drawer" aria-label="Contract debug">
      <div className="debug-header">
        <div>
          <p className="eyebrow">Contract</p>
          <h2>Request/Response Debug</h2>
        </div>
        <button className="icon-button secondary" onClick={onClose}>
          <XCircle aria-hidden="true" />
          Close
        </button>
      </div>
      <div className="debug-list">
        {stepOrder.map((key) => (
          <DebugStep key={key} log={logs[key]} />
        ))}
      </div>
    </aside>
  );
}

function DebugStep({ log }: { log: StepLog }) {
  return (
    <details className="debug-step" open={log.status === "failed"}>
      <summary>
        <span>{log.label}</span>
        <StatusBadge status={log.status} />
      </summary>
      <dl className="debug-meta">
        <dt>Endpoint</dt>
        <dd>{log.endpoint}</dd>
        <dt>HTTP</dt>
        <dd>{log.httpStatus || "n/a"}</dd>
        <dt>Elapsed</dt>
        <dd>{log.elapsedMs ? `${log.elapsedMs} ms` : "n/a"}</dd>
      </dl>
      {log.error && <ErrorView error={log.error} />}
      <JsonBlock title="Request" value={log.request} />
      <JsonBlock title="Response" value={log.response} />
    </details>
  );
}

function ErrorView({ error }: { error: ContractError | GenericApiError }) {
  if (isContractError(error)) {
    return (
      <div className="error-box">
        <AlertTriangle aria-hidden="true" />
        <div>
          <strong>
            {error.error_code} from {error.source_module}
          </strong>
          <p>{error.message}</p>
          <small>recoverable: {String(error.recoverable)}</small>
        </div>
      </div>
    );
  }
  return (
    <div className="error-box">
      <AlertTriangle aria-hidden="true" />
      <div>
        <strong>{error.status ? `HTTP ${error.status}` : "Request failed"}</strong>
        <p>{error.message}</p>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: StepStatus }) {
  const Icon =
    status === "running"
      ? Loader2
      : status === "passed"
        ? CheckCircle2
        : status === "failed"
          ? XCircle
          : status === "skipped"
            ? Play
            : AlertTriangle;
  return (
    <span className={`status-badge status-${status}`}>
      <Icon aria-hidden="true" />
      {status}
    </span>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong title={value}>{value}</strong>
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <p>{title}</p>
      <span>{detail}</span>
    </div>
  );
}

function EvidenceGroup({ title, evidence }: { title: string; evidence: EvidenceRef[] }) {
  if (evidence.length === 0) {
    return null;
  }
  return (
    <div className="evidence-group">
      <h4>
        {title} <span>{evidence.length}</span>
      </h4>
      <div className="evidence-list">
        {evidence.map((item) => (
          <EvidenceItem key={item.evidence_id} evidence={item} />
        ))}
      </div>
    </div>
  );
}

function EvidenceItem({ evidence }: { evidence: EvidenceRef }) {
  const location = evidence.file_path
    ? `${evidence.file_path}${lineRange(evidence)}`
    : evidence.source_id || evidence.source_type;
  return (
    <article className="evidence-item">
      <div>
        <strong>{evidence.evidence_id}</strong>
        <span>{evidence.source_type}</span>
      </div>
      <p>{location}</p>
      {evidence.excerpt && <blockquote>{evidence.excerpt}</blockquote>}
      <small>confidence {confidence(evidence.confidence)}</small>
    </article>
  );
}

function EvidenceBackedCard({ title, item }: { title: string; item: EvidenceBackedItem }) {
  return (
    <article className="finding-card">
      <h4>{title}</h4>
      <p>{item.summary}</p>
      <small>
        evidence {item.evidence_refs.length}
        {item.confidence !== null && item.confidence !== undefined
          ? ` · confidence ${confidence(item.confidence)}`
          : ""}
      </small>
    </article>
  );
}

function EvidenceBackedList({
  title,
  items,
}: {
  title: string;
  items: EvidenceBackedItem[];
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="finding-list">
      <h4>{title}</h4>
      {items.map((item, index) => (
        <EvidenceBackedCard key={`${title}-${index}`} title={`#${index + 1}`} item={item} />
      ))}
    </div>
  );
}

function PathList({ paths }: { paths: string[][] }) {
  if (paths.length === 0) {
    return null;
  }
  return (
    <div className="path-list">
      <h4>Graph paths</h4>
      {paths.map((path, index) => (
        <div className="path-row" key={`${path.join("-")}-${index}`}>
          {path.map((part, partIndex) => (
            <span key={`${part}-${partIndex}`}>{part}</span>
          ))}
        </div>
      ))}
    </div>
  );
}

function TagList({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <div className="tag-list">
      <h4>{title}</h4>
      <div>
        {values.map((value) => (
          <span key={value}>{value}</span>
        ))}
      </div>
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="json-block">
      <h4>{title}</h4>
      <pre>{value === undefined ? "n/a" : JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function normalizeRepoRequest(request: RepoIndexRequest): RepoIndexRequest {
  return {
    repo_id: request.repo_id.trim(),
    repo_uri: request.repo_uri.trim(),
    language_hint: request.language_hint.trim(),
    parser_profile: request.parser_profile.trim(),
    contract_version: request.contract_version.trim(),
  };
}

function normalizeAlertEvent(alert: AlertEvent): AlertEvent {
  const normalized: AlertEvent = {
    alert_id: alert.alert_id.trim(),
    repo_id: alert.repo_id.trim(),
    raw_log: alert.raw_log,
    occurred_at: alert.occurred_at.trim(),
    source: alert.source.trim(),
    contract_version: alert.contract_version.trim(),
  };
  if (alert.graph_id?.trim()) {
    normalized.graph_id = alert.graph_id.trim();
  }
  if (alert.stack_trace?.trim()) {
    normalized.stack_trace = alert.stack_trace;
  }
  if (alert.error_description?.trim()) {
    normalized.error_description = alert.error_description;
  }
  return normalized;
}

function unpackError(error: unknown): {
  httpStatus?: number;
  body: ContractError | GenericApiError;
} {
  if (error instanceof ApiRequestError) {
    if (isContractError(error.body)) {
      return { httpStatus: error.status, body: error.body };
    }
    return {
      httpStatus: error.status,
      body: {
        message: error.message,
        status: error.status,
        body: error.body,
      },
    };
  }
  if (error instanceof Error) {
    return { body: { message: error.message } };
  }
  return { body: { message: "Unknown request failure", body: error } };
}

function formatStepDetail(log: StepLog): string {
  if (log.status === "passed" && log.elapsedMs !== undefined) {
    return `${log.httpStatus || 200} · ${log.elapsedMs} ms`;
  }
  if (log.status === "failed" && log.error) {
    return isContractError(log.error) ? log.error.error_code : log.error.message;
  }
  return log.endpoint;
}

function confidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function lineRange(evidence: EvidenceRef): string {
  if (evidence.start_line && evidence.end_line) {
    return `:${evidence.start_line}-${evidence.end_line}`;
  }
  if (evidence.start_line) {
    return `:${evidence.start_line}`;
  }
  return "";
}
