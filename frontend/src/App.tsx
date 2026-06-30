import {
  Activity,
  AlertTriangle,
  Archive,
  BrainCircuit,
  ChevronDown,
  CheckCircle2,
  ClipboardList,
  Database,
  GitBranch,
  Github,
  Gitlab,
  KeyRound,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
  Settings,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  ApiRequestError,
  apiBase,
  deleteJson,
  getJson,
  isContractError,
  postJson,
} from "./api";
import type { RuntimeCredentials } from "./api";
import {
  defaultAlert,
  defaultRepoRequest,
  defaultSaveRequest,
} from "./defaults";
import type {
  AlertEvent,
  ContractError,
  DeleteGraphResponse,
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
  StoredGraph,
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

type WorkbenchSettings = {
  qwenApiKey: string;
  githubToken: string;
  gitlabToken: string;
};

type GraphListStatus = "idle" | "loading" | "failed";

const SETTINGS_STORAGE_KEY = "legacyPilot.workbench.settings.v1";

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

function emptyWorkbenchSettings(): WorkbenchSettings {
  return {
    qwenApiKey: "",
    githubToken: "",
    gitlabToken: "",
  };
}

function loadWorkbenchSettings(): WorkbenchSettings {
  if (typeof window === "undefined") {
    return emptyWorkbenchSettings();
  }
  const stored = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
  if (!stored) {
    return emptyWorkbenchSettings();
  }
  try {
    const parsed = JSON.parse(stored) as Partial<WorkbenchSettings>;
    return {
      qwenApiKey: typeof parsed.qwenApiKey === "string" ? parsed.qwenApiKey : "",
      githubToken: typeof parsed.githubToken === "string" ? parsed.githubToken : "",
      gitlabToken: typeof parsed.gitlabToken === "string" ? parsed.gitlabToken : "",
    };
  } catch {
    return emptyWorkbenchSettings();
  }
}

function saveWorkbenchSettings(settings: WorkbenchSettings) {
  if (typeof window === "undefined") {
    return;
  }
  const next = {
    qwenApiKey: settings.qwenApiKey.trim(),
    githubToken: settings.githubToken.trim(),
    gitlabToken: settings.gitlabToken.trim(),
  };
  if (!next.qwenApiKey && !next.githubToken && !next.gitlabToken) {
    window.localStorage.removeItem(SETTINGS_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(next));
}

function runtimeCredentials(settings: WorkbenchSettings): RuntimeCredentials {
  return {
    qwenApiKey: settings.qwenApiKey.trim() || undefined,
    githubToken: settings.githubToken.trim() || undefined,
    gitlabToken: settings.gitlabToken.trim() || undefined,
  };
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<WorkbenchSettings>(loadWorkbenchSettings);
  const [storedGraphs, setStoredGraphs] = useState<StoredGraph[]>([]);
  const [graphListStatus, setGraphListStatus] = useState<GraphListStatus>("idle");
  const [graphListError, setGraphListError] = useState<string | null>(null);
  const [graphDeleteTarget, setGraphDeleteTarget] = useState<StoredGraph | null>(null);
  const [graphDeleteRunning, setGraphDeleteRunning] = useState(false);

  useEffect(() => {
    void runHealth();
  }, []);

  useEffect(() => {
    saveWorkbenchSettings(settings);
  }, [settings]);

  const apiCredentials = useMemo(() => runtimeCredentials(settings), [settings]);
  const apiOptions = useMemo(
    () => ({
      credentials: apiCredentials,
    }),
    [apiCredentials],
  );

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
  const canUseExistingGraph =
    canUseApi && Boolean(alertEvent.repo_id.trim() && alertEvent.graph_id?.trim());
  const canSubmit =
    canUseApi &&
    Boolean(
      alertEvent.alert_id.trim() &&
        alertEvent.repo_id.trim() &&
        alertEvent.raw_log.trim(),
    );
  const canRunFullPipeline =
    canSubmit && Boolean(repoRequest.repo_uri.trim() || alertEvent.graph_id?.trim());
  const canBuildEvidence = canUseApi && incidentQuery !== null;
  const canGenerateRca = canUseApi && bundle !== null;
  const canReviewRca = canUseApi && rcaReport !== null;
  const canSave =
    canUseApi &&
    reviewedReport !== null &&
    saveDraft.user_confirmation &&
    saveDraft.fix_outcome.trim().length > 0 &&
    saveDraft.retention_policy.trim().length > 0;
  const isPipelineRunning = stepOrder.some(
    (key) => key !== "health" && stepLogs[key].status === "running",
  );
  const isUsingExistingGraphRunning =
    isPipelineRunning && Boolean(alertEvent.graph_id?.trim()) && !repoRequest.repo_uri.trim();
  const isHealthRunning = stepLogs.health.status === "running";
  const isIndexing = stepLogs.index.status === "running";
  const isSubmittingAlert = stepLogs.submit.status === "running";
  const isBuildingEvidence = stepLogs.evidence.status === "running";
  const isGeneratingRca = stepLogs.generate.status === "running";
  const isReviewingRca = stepLogs.review.status === "running";
  const isSavingIncident =
    stepLogs.save.status === "running" || stepLogs.readback.status === "running";

  async function runHealth(): Promise<HealthResponse | null> {
    return runStep<HealthResponse>(
      "health",
      undefined,
      () => getJson<HealthResponse>("/health", apiOptions),
      (data) => {
        setHealth(data);
        void loadStoredGraphs();
      },
    );
  }

  async function loadStoredGraphs() {
    setGraphListStatus("loading");
    setGraphListError(null);
    try {
      const result = await getJson<StoredGraph[]>("/v1/graphs", apiOptions);
      setStoredGraphs(result.data);
      setGraphListStatus("idle");
    } catch (error) {
      const unpacked = unpackError(error);
      setGraphListError(unpacked.body.message);
      setGraphListStatus("failed");
    }
  }

  async function runIndex(): Promise<GraphSnapshot | null> {
    const request = normalizeRepoRequest(repoRequest);
    return runStep<GraphSnapshot>(
      "index",
      request,
      () => postJson<GraphSnapshot>("/v1/repos/index", request, apiOptions),
      (data) => {
        setSnapshot(data);
        setAlertEvent((current) => ({
          ...current,
          repo_id: data.repo_id,
          graph_id: data.graph_id,
        }));
        void loadStoredGraphs();
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

  function selectStoredGraph(graph: StoredGraph) {
    setRepoRequest((current) => ({
      ...current,
      repo_id: graph.repo_id,
    }));
    setAlertEvent((current) => ({
      ...current,
      repo_id: graph.repo_id,
      graph_id: graph.graph_id,
    }));
    setSnapshot(null);
    clearPipelineAfter("index");
  }

  async function confirmDeleteGraph() {
    if (!graphDeleteTarget || graphDeleteTarget.incident_memory_count > 0) {
      return;
    }
    const target = graphDeleteTarget;
    setGraphDeleteRunning(true);
    try {
      await deleteJson<DeleteGraphResponse>(
        `/v1/graphs/${encodeURIComponent(target.repo_id)}/${encodeURIComponent(target.graph_id)}`,
        apiOptions,
      );
      setGraphDeleteTarget(null);
      setStoredGraphs((graphs) =>
        graphs.filter(
          (graph) =>
            graph.repo_id !== target.repo_id || graph.graph_id !== target.graph_id,
        ),
      );
      if (alertEvent.repo_id === target.repo_id && alertEvent.graph_id === target.graph_id) {
        setAlertEvent((current) => ({ ...current, graph_id: "" }));
      }
      void loadStoredGraphs();
    } catch (error) {
      const unpacked = unpackError(error);
      setGraphListError(unpacked.body.message);
      setGraphListStatus("failed");
      setGraphDeleteTarget(null);
    } finally {
      setGraphDeleteRunning(false);
    }
  }

  async function runSubmitAlert(override?: Partial<AlertEvent>): Promise<IncidentQuery | null> {
    const request = normalizeAlertEvent({ ...alertEvent, ...override });
    return runStep<IncidentQuery>(
      "submit",
      request,
      () => postJson<IncidentQuery>("/v1/alerts/submit", request, apiOptions),
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
      () => postJson<EvidenceBundle>("/v1/evidence-bundles/build", input, apiOptions),
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
      () => postJson<RCAReport>("/v1/rca/generate", input, apiOptions),
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
      () => postJson<ReviewedRCAReport>("/v1/rca/review", input, apiOptions),
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
      () => postJson<IncidentRecord>("/v1/incidents/save", request, apiOptions),
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
      () => getJson<IncidentRecord>(`/v1/incidents/${encodeURIComponent(incidentId)}`, apiOptions),
      (data) => setPersistedIncidentRecord(data),
    );
  }

  async function runFullPipeline() {
    if (!canRunFullPipeline) {
      return;
    }
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
          <button
            className="icon-button secondary"
            data-testid="settings-button"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings aria-hidden="true" />
            Settings
          </button>
          <button
            className="icon-button secondary"
            disabled={isHealthRunning}
            onClick={() => void runHealth()}
          >
            <ButtonIcon icon={Server} loading={isHealthRunning} />
            Health
          </button>
          <button className="icon-button secondary" onClick={resetAll}>
            <RotateCcw aria-hidden="true" />
            Reset
          </button>
          <button
            className="icon-button primary"
            data-testid="run-full-pipeline"
            disabled={!canRunFullPipeline || isPipelineRunning}
            onClick={() => void runFullPipeline()}
          >
            <ButtonIcon icon={Play} loading={isPipelineRunning} />
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
            canUseExistingGraph={canUseExistingGraph}
            graphListError={graphListError}
            graphListStatus={graphListStatus}
            isIndexing={isIndexing}
            isUsingExistingGraphRunning={isUsingExistingGraphRunning}
            selectedGraphId={alertEvent.graph_id || ""}
            storedGraphs={storedGraphs}
            onChange={setRepoField}
            onIndex={() => void runIndex()}
            onReloadGraphs={() => void loadStoredGraphs()}
            onRequestDeleteGraph={setGraphDeleteTarget}
            onSelectGraph={selectStoredGraph}
            onSkip={skipIndex}
          />
          <AlertForm
            value={alertEvent}
            canSubmit={canSubmit}
            isSubmitting={isSubmittingAlert}
            onChange={setAlertField}
            onSubmit={() => void runSubmitAlert()}
          />
          <SaveForm
            value={saveDraft}
            canSave={canSave}
            isSaving={isSavingIncident}
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
              disabled={!canBuildEvidence || isBuildingEvidence}
              onClick={() => void runBuildEvidence()}
            >
              <ButtonIcon icon={Database} loading={isBuildingEvidence} />
              Build evidence
            </button>
          </div>
          <SnapshotSummary snapshot={snapshot} />
          <IncidentQuerySummary query={incidentQuery} />
          <EvidenceBundleView bundle={bundle} />
          <div className="inline-actions">
            <button
              className="icon-button secondary"
              disabled={!canGenerateRca || isGeneratingRca}
              onClick={() => void runGenerateRca()}
            >
              <ButtonIcon icon={BrainCircuit} loading={isGeneratingRca} />
              Generate RCA
            </button>
            <button
              className="icon-button secondary"
              disabled={!canReviewRca || isReviewingRca}
              onClick={() => void runReviewRca()}
            >
              <ButtonIcon icon={ShieldCheck} loading={isReviewingRca} />
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
      <SettingsModal
        open={settingsOpen}
        value={settings}
        onChange={setSettings}
        onClear={() => setSettings(emptyWorkbenchSettings())}
        onClose={() => setSettingsOpen(false)}
      />
      <GraphDeleteModal
        deleting={graphDeleteRunning}
        graph={graphDeleteTarget}
        onCancel={() => setGraphDeleteTarget(null)}
        onConfirm={() => void confirmDeleteGraph()}
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

function graphLabel(graph: StoredGraph): string {
  const updated = new Date(graph.updated_at).toLocaleString();
  return `${graph.repo_id} / ${graph.graph_id} / ${updated}`;
}

function ButtonIcon({ icon: Icon, loading = false }: { icon: LucideIcon; loading?: boolean }) {
  const ActualIcon = loading ? Loader2 : Icon;
  return <ActualIcon aria-hidden="true" className={loading ? "spin" : undefined} />;
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
  canUseExistingGraph,
  graphListError,
  graphListStatus,
  isIndexing,
  isUsingExistingGraphRunning,
  selectedGraphId,
  storedGraphs,
  onChange,
  onIndex,
  onReloadGraphs,
  onRequestDeleteGraph,
  onSelectGraph,
  onSkip,
}: {
  value: RepoIndexRequest;
  canIndex: boolean;
  canUseExistingGraph: boolean;
  graphListError: string | null;
  graphListStatus: GraphListStatus;
  isIndexing: boolean;
  isUsingExistingGraphRunning: boolean;
  selectedGraphId: string;
  storedGraphs: StoredGraph[];
  onChange: (field: keyof RepoIndexRequest, value: string) => void;
  onIndex: () => void;
  onReloadGraphs: () => void;
  onRequestDeleteGraph: (graph: StoredGraph) => void;
  onSelectGraph: (graph: StoredGraph) => void;
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
          placeholder="file:///path/to/repo or https://github.com/owner/repo or https://gitlab.com/group/repo"
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
      <ExistingGraphPicker
        error={graphListError}
        graphs={storedGraphs}
        loading={graphListStatus === "loading"}
        selectedGraphId={selectedGraphId}
        onDelete={onRequestDeleteGraph}
        onRefresh={onReloadGraphs}
        onSelect={onSelectGraph}
      />
      <div className="inline-actions">
        <button
          className="icon-button secondary"
          disabled={!canIndex || isIndexing}
          onClick={onIndex}
        >
          <ButtonIcon icon={Database} loading={isIndexing} />
          Index repo
        </button>
        <button
          className="icon-button ghost"
          disabled={!canUseExistingGraph || isUsingExistingGraphRunning}
          onClick={onSkip}
        >
          <ButtonIcon icon={Play} loading={isUsingExistingGraphRunning} />
          Use existing graph
        </button>
      </div>
    </div>
  );
}

function ExistingGraphPicker({
  error,
  graphs,
  loading,
  selectedGraphId,
  onDelete,
  onRefresh,
  onSelect,
}: {
  error: string | null;
  graphs: StoredGraph[];
  loading: boolean;
  selectedGraphId: string;
  onDelete: (graph: StoredGraph) => void;
  onRefresh: () => void;
  onSelect: (graph: StoredGraph) => void;
}) {
  const [open, setOpen] = useState(false);
  const selectedGraph = graphs.find((graph) => graph.graph_id === selectedGraphId);
  return (
    <div className="graph-picker">
      <div className="graph-picker-heading">
        <span>Existing graphs</span>
        <button
          aria-label="Refresh existing graphs"
          className="icon-button ghost icon-only"
          disabled={loading}
          onClick={onRefresh}
          type="button"
        >
          <ButtonIcon icon={RefreshCw} loading={loading} />
        </button>
      </div>
      <button
        aria-expanded={open}
        className="graph-picker-trigger"
        data-testid="existing-graph-trigger"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span>
          {selectedGraph
            ? graphLabel(selectedGraph)
            : selectedGraphId
              ? selectedGraphId
              : "Select existing graph"}
        </span>
        <ChevronDown aria-hidden="true" />
      </button>
      {open && (
        <div className="graph-options" role="listbox">
          {graphs.length === 0 && (
            <div className="graph-empty">
              {loading ? "Loading graphs..." : "No persisted graphs"}
            </div>
          )}
          {graphs.map((graph) => (
            <div
              className={`graph-option ${graph.graph_id === selectedGraphId ? "selected" : ""}`}
              key={`${graph.repo_id}:${graph.graph_id}`}
              role="option"
              aria-selected={graph.graph_id === selectedGraphId}
            >
              <button
                className="graph-option-main"
                onClick={() => {
                  onSelect(graph);
                  setOpen(false);
                }}
                type="button"
              >
                <strong>{graphLabel(graph)}</strong>
                <small>
                  {graph.node_count} nodes / {graph.edge_count} edges /{" "}
                  {graph.incident_memory_count} incident memories
                </small>
              </button>
              <button
                aria-label={`Delete graph ${graph.graph_id}`}
                className="graph-delete-button"
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(graph);
                  setOpen(false);
                }}
                type="button"
              >
                <X aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      )}
      {error && <p className="inline-error">{error}</p>}
    </div>
  );
}

function GraphDeleteModal({
  deleting,
  graph,
  onCancel,
  onConfirm,
}: {
  deleting: boolean;
  graph: StoredGraph | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!graph) {
    return null;
  }
  const blocked = graph.incident_memory_count > 0;
  return (
    <div className="settings-backdrop" onClick={deleting ? undefined : onCancel}>
      <section
        aria-labelledby="graph-delete-title"
        aria-modal="true"
        className="settings-modal graph-delete-modal"
        data-testid="graph-delete-modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="settings-header">
          <div>
            <p className="eyebrow">GraphSnapshot</p>
            <h2 id="graph-delete-title">{blocked ? "Graph in use" : "Delete graph"}</h2>
          </div>
          <button
            className="icon-button secondary"
            disabled={deleting}
            onClick={onCancel}
            type="button"
          >
            <XCircle aria-hidden="true" />
            Close
          </button>
        </div>
        <div className="graph-delete-body">
          <Metric label="repo_id" value={graph.repo_id} />
          <Metric label="graph_id" value={graph.graph_id} />
          <Metric label="incident memories" value={graph.incident_memory_count.toString()} />
          {blocked ? (
            <div className="warning-box">
              <AlertTriangle aria-hidden="true" />
              <span>
                This graph is used by {graph.incident_memory_count} incident memory
                {graph.incident_memory_count === 1 ? "" : " records"}. Delete is blocked.
              </span>
            </div>
          ) : (
            <p className="summary-text">
              This removes the persisted GraphSnapshot payload. Incident memory records are not
              deleted by this action.
            </p>
          )}
        </div>
        <div className="settings-actions">
          <button
            className="icon-button secondary"
            disabled={deleting}
            onClick={onCancel}
            type="button"
          >
            <XCircle aria-hidden="true" />
            Cancel
          </button>
          {!blocked && (
            <button
              className="icon-button danger"
              disabled={deleting}
              onClick={onConfirm}
              type="button"
            >
              <ButtonIcon icon={Trash2} loading={deleting} />
              Delete
            </button>
          )}
        </div>
      </section>
    </div>
  );
}

function AlertForm({
  value,
  canSubmit,
  isSubmitting,
  onChange,
  onSubmit,
}: {
  value: AlertEvent;
  canSubmit: boolean;
  isSubmitting: boolean;
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
      <button
        className="icon-button secondary"
        disabled={!canSubmit || isSubmitting}
        onClick={onSubmit}
      >
        <ButtonIcon icon={Activity} loading={isSubmitting} />
        Submit alert
      </button>
    </div>
  );
}

function SaveForm({
  value,
  canSave,
  isSaving,
  onChange,
  onSave,
}: {
  value: ReturnType<typeof defaultSaveRequest>;
  canSave: boolean;
  isSaving: boolean;
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
        disabled={!canSave || isSaving}
        onClick={onSave}
      >
        <ButtonIcon icon={Save} loading={isSaving} />
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
        <Metric label="graph_id" value={report.graph_id || "none"} />
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
        <Metric label="graph_id" value={report.graph_id || "none"} />
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
        <Metric label="graph_id" value={record.graph_id || "none"} />
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
        <Metric label="graph_id" value={record.graph_id || "none"} />
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

function SettingsModal({
  open,
  value,
  onChange,
  onClear,
  onClose,
}: {
  open: boolean;
  value: WorkbenchSettings;
  onChange: (settings: WorkbenchSettings) => void;
  onClear: () => void;
  onClose: () => void;
}) {
  if (!open) {
    return null;
  }
  const update = (field: keyof WorkbenchSettings, nextValue: string) => {
    onChange({ ...value, [field]: nextValue });
  };
  return (
    <div className="settings-backdrop" onClick={onClose}>
      <section
        aria-labelledby="settings-title"
        aria-modal="true"
        className="settings-modal"
        data-testid="settings-modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="settings-header">
          <div>
            <p className="eyebrow">Settings</p>
            <h2 id="settings-title">Connections</h2>
          </div>
          <button className="icon-button secondary" onClick={onClose}>
            <XCircle aria-hidden="true" />
            Close
          </button>
        </div>
        <div className="settings-grid">
          <section className="settings-section" aria-labelledby="qwen-settings-heading">
            <div className="block-title">
              <KeyRound aria-hidden="true" />
              <h3 id="qwen-settings-heading">Qwen</h3>
            </div>
            <label>
              API key
              <input
                autoComplete="off"
                data-testid="qwen-api-key-input"
                onChange={(event) => update("qwenApiKey", event.target.value)}
                placeholder="sk-..."
                type="password"
                value={value.qwenApiKey}
              />
            </label>
            <ConnectionState connected={Boolean(value.qwenApiKey.trim())} />
          </section>

          <section className="settings-section" aria-labelledby="github-settings-heading">
            <div className="block-title">
              <Github aria-hidden="true" />
              <h3 id="github-settings-heading">GitHub account</h3>
            </div>
            <label>
              Token
              <input
                autoComplete="off"
                data-testid="github-token-input"
                onChange={(event) => update("githubToken", event.target.value)}
                placeholder="github_pat_..."
                type="password"
                value={value.githubToken}
              />
            </label>
            <div className="settings-row">
              <ConnectionState connected={Boolean(value.githubToken.trim())} />
              <button
                className="icon-button secondary"
                onClick={() => openExternal("https://github.com/settings/tokens")}
              >
                <Github aria-hidden="true" />
                Login
              </button>
            </div>
          </section>

          <section className="settings-section" aria-labelledby="gitlab-settings-heading">
            <div className="block-title">
              <Gitlab aria-hidden="true" />
              <h3 id="gitlab-settings-heading">GitLab account</h3>
            </div>
            <label>
              Token
              <input
                autoComplete="off"
                data-testid="gitlab-token-input"
                onChange={(event) => update("gitlabToken", event.target.value)}
                placeholder="glpat-..."
                type="password"
                value={value.gitlabToken}
              />
            </label>
            <div className="settings-row">
              <ConnectionState connected={Boolean(value.gitlabToken.trim())} />
              <button
                className="icon-button secondary"
                onClick={() =>
                  openExternal("https://gitlab.com/-/user_settings/personal_access_tokens")
                }
              >
                <Gitlab aria-hidden="true" />
                Login
              </button>
            </div>
          </section>
        </div>
        <div className="settings-actions">
          <button className="icon-button secondary" onClick={onClear}>
            <RotateCcw aria-hidden="true" />
            Clear
          </button>
          <button className="icon-button primary" onClick={onClose}>
            <Save aria-hidden="true" />
            Save
          </button>
        </div>
      </section>
    </div>
  );
}

function ConnectionState({ connected }: { connected: boolean }) {
  return (
    <span className={`connection-state ${connected ? "connected" : ""}`}>
      {connected ? "Saved locally" : "Not connected"}
    </span>
  );
}

function openExternal(url: string) {
  window.open(url, "_blank", "noopener,noreferrer");
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
