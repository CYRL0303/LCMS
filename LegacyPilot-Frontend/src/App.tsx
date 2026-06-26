import {
  Activity,
  AlertTriangle,
  Bot,
  Boxes,
  Braces,
  ChevronDown,
  ChevronRight,
  CircleDot,
  FileCode2,
  FolderGit2,
  GitBranch,
  LayoutDashboard,
  Network,
  Paperclip,
  PlugZap,
  Send,
  SearchCode,
  UserRound
} from 'lucide-react';
import { useEffect, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';

type Metric = {
  label: string;
  value: string;
  description: string;
};

type NavItem = {
  label: string;
  page: PageKey;
  icon: React.ComponentType<{ size?: number }>;
};

type NavGroup = {
  title: string;
  items: NavItem[];
};

type PageKey =
  | 'overview'
  | 'onboarding'
  | 'repository'
  | 'graph'
  | 'endpoints'
  | 'incidents'
  | 'agent';

type Endpoint = {
  method: string;
  path: string;
  controller: string;
  handler: string;
  risk: 'Low' | 'Medium' | 'High';
};

const metrics: Metric[] = [
  { label: 'Projects', value: '0', description: 'No repositories indexed yet' },
  { label: 'Code Nodes', value: '0', description: 'Classes, methods, endpoints' },
  { label: 'Endpoints', value: '0', description: 'Spring MVC routes detected' },
  { label: 'Incidents', value: '0', description: 'Analysis cases opened' }
];

const navGroups: NavGroup[] = [
  {
    title: 'Workspace',
    items: [
      { label: 'Home', page: 'overview', icon: LayoutDashboard },
      { label: 'Onboarding', page: 'onboarding', icon: PlugZap }
    ]
  },
  {
    title: 'Project',
    items: [
      { label: 'Repository', page: 'repository', icon: FolderGit2 },
      { label: 'Code Graph', page: 'graph', icon: Network },
      { label: 'Endpoints', page: 'endpoints', icon: Braces },
      { label: 'Incidents', page: 'incidents', icon: AlertTriangle }
    ]
  }
];

const workflowItems = [
  {
    title: 'Onboard local repository',
    description: 'Register a Java or Spring project path and prepare it for indexing.',
    icon: FolderGit2
  },
  {
    title: 'Extract code facts',
    description: 'Build the first graph from packages, classes, methods, and endpoints.',
    icon: SearchCode
  },
  {
    title: 'Trace maintenance evidence',
    description: 'Use structured facts to support incident analysis and change planning.',
    icon: Activity
  }
];

const sampleEndpoints: Endpoint[] = [
  {
    method: 'POST',
    path: '/api/onboarding/local-project',
    controller: 'ProjectController',
    handler: 'onboardLocalProject',
    risk: 'Medium'
  },
  {
    method: 'GET',
    path: '/api/projects/{projectId}/graph/summary',
    controller: 'ProjectController',
    handler: 'getGraphSummary',
    risk: 'Low'
  },
  {
    method: 'GET',
    path: '/api/incidents/{incidentId}/analysis',
    controller: 'IncidentController',
    handler: 'getIncidentAnalysis',
    risk: 'High'
  }
];

function getPageFromHash(): PageKey {
  const hash = window.location.hash.replace(/^#\/?/, '');

  if (hash === 'home' || hash === '') {
    return 'overview';
  }

  const validPages: PageKey[] = [
    'overview',
    'onboarding',
    'repository',
    'graph',
    'endpoints',
    'incidents',
    'agent'
  ];

  return validPages.includes(hash as PageKey) ? (hash as PageKey) : 'overview';
}

function getHashForPage(page: PageKey) {
  return page === 'overview' ? '#/home' : `#/${page}`;
}

export function App() {
  const [activePage, setActivePage] = useState<PageKey>(() => getPageFromHash());
  const [isAgentOpen, setIsAgentOpen] = useState(false);
  const [agentWidth, setAgentWidth] = useState(430);
  const [isOnboardingComplete, setIsOnboardingComplete] = useState(
    () => window.localStorage.getItem('legacyPilot.onboardingComplete') === 'true'
  );
  const [localProjectPath, setLocalProjectPath] = useState(
    () => window.localStorage.getItem('legacyPilot.localProjectPath') ?? 'D:\\Hackathon\\LegacyPilot'
  );

  useEffect(() => {
    const handleHashChange = () => {
      setActivePage(getPageFromHash());
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    window.localStorage.setItem('legacyPilot.onboardingComplete', String(isOnboardingComplete));
  }, [isOnboardingComplete]);

  useEffect(() => {
    window.localStorage.setItem('legacyPilot.localProjectPath', localProjectPath);
  }, [localProjectPath]);

  const navigateTo = (page: PageKey) => {
    const nextHash = getHashForPage(page);

    if (window.location.hash === nextHash) {
      setActivePage(page);
      return;
    }

    window.location.hash = nextHash;
  };

  const startAgentResize = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const nextWidth = window.innerWidth - moveEvent.clientX;
      setAgentWidth(Math.min(Math.max(nextWidth, 360), 720));
    };

    const handleMouseUp = () => {
      document.body.classList.remove('is-resizing-agent');
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    document.body.classList.add('is-resizing-agent');
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Boxes size={22} />
          </div>
          <div>
            <p className="brand-name">LegacyPilot</p>
            <p className="brand-caption">Maintenance Workbench</p>
          </div>
        </div>

        <nav className="nav-list" aria-label="Primary navigation">
          {navGroups.map((group) => (
            <section className="nav-section" key={group.title}>
              <div className="nav-section-title">
                <span>{group.title}</span>
                {group.title === 'Project' && <ChevronDown size={14} />}
              </div>
              <div className="nav-section-items">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      className={activePage === item.page ? 'nav-item active' : 'nav-item'}
                      key={item.label}
                      onClick={() => navigateTo(item.page)}
                    >
                      <Icon size={18} />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </nav>

        <div className="sidebar-status">
          <div className="status-row">
            <CircleDot size={14} />
            <span>Frontend shell</span>
          </div>
          <p>No API connection configured.</p>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">Track 4 Autopilot Agent</p>
            <h1>Java/Spring Legacy Maintenance Workbench</h1>
          </div>
          <div className="topbar-actions">
            <div className="repo-chip">
              <GitBranch size={16} />
              <span>Local demo workspace</span>
            </div>
            <button className="user-menu" aria-label="Open user menu">
              <span className="user-avatar">
                <UserRound size={17} />
              </span>
              <span className="user-copy">
                <strong>Demo User</strong>
                <small>Signed in shell</small>
              </span>
              <ChevronDown size={15} />
            </button>
          </div>
        </header>

        {activePage === 'overview' && <OverviewPage onNavigate={navigateTo} />}
        {activePage === 'onboarding' && (
          <OnboardingPage
            isComplete={isOnboardingComplete}
            localPath={localProjectPath}
            onComplete={() => setIsOnboardingComplete(true)}
            onLocalPathChange={setLocalProjectPath}
            onNavigate={navigateTo}
          />
        )}
        {activePage === 'endpoints' && <EndpointsPage />}
        {activePage !== 'overview' && activePage !== 'onboarding' && activePage !== 'endpoints' && (
          <PlaceholderPage page={activePage} />
        )}
      </main>

      <button
        className={isAgentOpen ? 'agent-fab hidden' : 'agent-fab'}
        onClick={() => setIsAgentOpen(true)}
        aria-label="Open LegacyPilot Agent"
      >
        <Bot size={22} />
      </button>

      <aside
        className={isAgentOpen ? 'agent-drawer open' : 'agent-drawer'}
        style={{ width: `min(${agentWidth}px, 100vw)` }}
        aria-label="Agent panel"
      >
        <div
          className="agent-resize-handle"
          onMouseDown={startAgentResize}
          aria-label="Resize agent panel"
          role="separator"
        />
        <div className="agent-drawer-header">
          <div>
            <p className="section-kicker">Autopilot</p>
            <h3>LegacyPilot Agent</h3>
          </div>
          <button className="agent-close" onClick={() => setIsAgentOpen(false)} aria-label="Close agent">
            <ChevronRight size={20} />
          </button>
        </div>

        <section className="agent-context">
          <div className="agent-context-row">
            <span>Current view</span>
            <strong>{getPageLabel(activePage)}</strong>
          </div>
          <div className="agent-context-row">
            <span>Project</span>
            <strong>Local demo workspace</strong>
          </div>
          <div className="agent-context-row">
            <span>Graph status</span>
            <strong>Static shell</strong>
          </div>
        </section>

        <section className="agent-welcome">
          <div className="agent-orbit">
            <Bot size={28} />
          </div>
          <h4>Hello, I am LegacyPilot Agent</h4>
          <p>I can explain code facts, trace endpoint impact, and prepare maintenance checklists.</p>
        </section>

        <section className="prompt-list" aria-label="Suggested prompts">
          <button>Explain the selected endpoint</button>
          <button>Find possible failure points</button>
          <button>Show impact scope</button>
          <button>Generate a maintenance checklist</button>
        </section>

        <div className="agent-chat">
          <div className="agent-message">
            <strong>Agent</strong>
            <p>
              Open an endpoint, graph node, or incident, then ask a question. I will use that context
              when the backend graph is connected.
            </p>
          </div>
        </div>

        <form className="agent-composer">
          <button type="button" aria-label="Attach evidence">
            <Paperclip size={18} />
          </button>
          <input placeholder="Ask about this project..." aria-label="Ask the agent" />
          <button type="button" aria-label="Send message">
            <Send size={18} />
          </button>
        </form>
      </aside>
    </div>
  );
}

function getPageLabel(page: PageKey) {
  const labels: Record<PageKey, string> = {
    overview: 'Home',
    onboarding: 'Onboarding',
    repository: 'Repository',
    graph: 'Code Graph',
    endpoints: 'Endpoints',
    incidents: 'Incidents',
    agent: 'Agent Workspace'
  };

  return labels[page];
}

function OverviewPage({ onNavigate }: { onNavigate: (page: PageKey) => void }) {
  return (
    <>
      <section className="hero-section">
          <div className="hero-copy">
            <p className="section-kicker">Home</p>
            <h2>Build code facts before asking the agent.</h2>
            <p>
              LegacyPilot indexes local Java projects, extracts a traceable code graph, and prepares
              evidence for incident analysis, migration planning, and maintenance decisions.
            </p>
            <div className="hero-actions">
              <button className="primary-action" onClick={() => onNavigate('onboarding')}>
                <PlugZap size={18} />
                Onboard project
              </button>
              <button className="secondary-action" onClick={() => onNavigate('graph')}>
                <Network size={18} />
                View graph
              </button>
            </div>
          </div>

          <div className="index-panel" aria-label="Indexing status preview">
            <div className="index-header">
              <span>Indexing Pipeline</span>
              <strong>Not started</strong>
            </div>
            <div className="pipeline">
              <div className="pipeline-step ready">Repository</div>
              <div className="pipeline-step">Java files</div>
              <div className="pipeline-step">Endpoints</div>
              <div className="pipeline-step">Evidence graph</div>
            </div>
          </div>
      </section>

      <section className="metric-grid" aria-label="Project metrics">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <p>{metric.label}</p>
            <strong>{metric.value}</strong>
            <span>{metric.description}</span>
          </article>
        ))}
      </section>

      <section className="content-grid">
        <article className="panel workflow-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Workflow</p>
              <h3>Recommended first pass</h3>
            </div>
          </div>

          <div className="workflow-list">
            {workflowItems.map((item, index) => {
              const Icon = item.icon;
              return (
                <div className="workflow-item" key={item.title}>
                  <div className="workflow-icon">
                    <Icon size={19} />
                  </div>
                  <div>
                    <span>0{index + 1}</span>
                    <h4>{item.title}</h4>
                    <p>{item.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </article>

        <article className="panel empty-panel">
          <div className="empty-icon">
            <FileCode2 size={30} />
          </div>
          <h3>No project indexed yet</h3>
          <p>
            Start by onboarding a local Java/Spring repository. The dashboard will show real files,
            endpoints, code nodes, and evidence links after indexing is connected.
          </p>
          <button className="text-action" onClick={() => onNavigate('onboarding')}>
            Open onboarding
          </button>
        </article>
      </section>
    </>
  );
}

function OnboardingPage({
  isComplete,
  localPath,
  onComplete,
  onLocalPathChange,
  onNavigate
}: {
  isComplete: boolean;
  localPath: string;
  onComplete: () => void;
  onLocalPathChange: (path: string) => void;
  onNavigate: (page: PageKey) => void;
}) {
  const steps = [
    'Validate local path',
    'Read Git metadata',
    'Scan Java and config files',
    'Extract Spring endpoints',
    'Prepare code graph summary'
  ];

  return (
    <section className="page-stack">
      <div className="page-title-row">
        <div>
          <p className="section-kicker">Workspace / Onboarding</p>
          <h2>Onboard a local Java project</h2>
          <p>
            Register a local repository path and prepare it for code fact extraction. This screen is
            static for now, but mirrors the backend onboarding flow.
          </p>
        </div>
        <button className="secondary-action" onClick={() => onNavigate('overview')}>
          Back to Home
        </button>
      </div>

      <div className="onboarding-layout">
        <article className="panel onboarding-form-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Local Repository</p>
              <h3>Project source</h3>
            </div>
          </div>

          <label className="field-label" htmlFor="local-path">
            Local project path
          </label>
          <div className="path-input-row">
            <input
              id="local-path"
              value={localPath}
              onChange={(event) => onLocalPathChange(event.target.value)}
              placeholder="D:\\Hackathon\\LegacyPilot"
            />
            <button className="secondary-action" type="button">
              Browse
            </button>
          </div>

          <div className="form-grid">
            <div>
              <span>Project Name</span>
              <strong>LegacyPilot</strong>
            </div>
            <div>
              <span>Scan Mode</span>
              <strong>Quick Java/Spring scan</strong>
            </div>
            <div>
              <span>Target Backend API</span>
              <strong>POST /api/onboarding/local-project</strong>
            </div>
            <div>
              <span>Connection</span>
              <strong>Static demo only</strong>
            </div>
          </div>

          <button className="primary-action onboarding-start" onClick={onComplete}>
            <PlugZap size={18} />
            {isComplete ? 'Run onboarding again' : 'Start onboarding'}
          </button>
        </article>

        <article className="panel onboarding-status-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Pipeline Preview</p>
              <h3>{isComplete ? 'Demo onboarding complete' : 'Waiting to start'}</h3>
            </div>
          </div>

          <div className="onboarding-steps">
            {steps.map((step, index) => (
              <div className={isComplete ? 'onboarding-step done' : 'onboarding-step'} key={step}>
                <span>{index + 1}</span>
                <div>
                  <strong>{step}</strong>
                  <p>{isComplete ? 'Completed in static preview' : 'Pending'}</p>
                </div>
              </div>
            ))}
          </div>

          {isComplete && (
            <div className="onboarding-result">
              <h4>Mock result</h4>
              <p>
                LegacyPilot was registered from <strong>{localPath}</strong>. You can now inspect
                the project shell or jump into endpoint analysis.
              </p>
              <div className="hero-actions">
                <button className="primary-action" onClick={() => onNavigate('repository')}>
                  View repository
                </button>
                <button className="secondary-action" onClick={() => onNavigate('endpoints')}>
                  View endpoints
                </button>
              </div>
            </div>
          )}
        </article>
      </div>
    </section>
  );
}

function EndpointsPage() {
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint>(sampleEndpoints[0]);

  return (
    <section className="page-stack">
      <div className="page-title-row">
        <div>
          <p className="section-kicker">Project / Endpoints</p>
          <h2>Endpoint Analysis</h2>
          <p>
            Inspect Spring request mappings and trace each API entry point back to controller,
            handler, downstream calls, and evidence.
          </p>
        </div>
        <button className="secondary-action">
          <SearchCode size={18} />
          Analyze selected
        </button>
      </div>

      <div className="endpoint-layout">
        <article className="panel endpoint-list-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Indexed Routes</p>
              <h3>Detected endpoints</h3>
            </div>
          </div>

          <div className="endpoint-table">
            {sampleEndpoints.map((endpoint) => (
              <button
                className={
                  endpoint.path === selectedEndpoint.path
                    ? 'endpoint-row selected'
                    : 'endpoint-row'
                }
                key={endpoint.path}
                onClick={() => setSelectedEndpoint(endpoint)}
              >
                <span className={`method-badge method-${endpoint.method.toLowerCase()}`}>
                  {endpoint.method}
                </span>
                <span className="endpoint-path">{endpoint.path}</span>
                <span className="endpoint-controller">{endpoint.controller}</span>
              </button>
            ))}
          </div>
        </article>

        <article className="panel endpoint-detail-panel">
          <div className="endpoint-detail-header">
            <span className={`method-badge method-${selectedEndpoint.method.toLowerCase()}`}>
              {selectedEndpoint.method}
            </span>
            <div>
              <h3>{selectedEndpoint.path}</h3>
              <p>
                {selectedEndpoint.controller}.{selectedEndpoint.handler}()
              </p>
            </div>
          </div>

          <div className="detail-grid">
            <div>
              <span>Controller</span>
              <strong>{selectedEndpoint.controller}</strong>
            </div>
            <div>
              <span>Handler Method</span>
              <strong>{selectedEndpoint.handler}</strong>
            </div>
            <div>
              <span>Source</span>
              <strong>src/main/java/.../{selectedEndpoint.controller}.java:42</strong>
            </div>
            <div>
              <span>Risk</span>
              <strong>{selectedEndpoint.risk}</strong>
            </div>
          </div>

          <div className="analysis-columns">
            <section>
              <h4>Call Chain</h4>
              <ol className="trace-list">
                <li>{selectedEndpoint.controller}.{selectedEndpoint.handler}()</li>
                <li>ProjectService.resolveRepository()</li>
                <li>JavaCodeAnalysisService.buildGraph()</li>
                <li>CodeKnowledgeClient.indexRepository()</li>
              </ol>
            </section>

            <section>
              <h4>Evidence</h4>
              <div className="evidence-list">
                <span>@RequestMapping annotation</span>
                <span>Controller class declaration</span>
                <span>Handler method declaration</span>
                <span>Service dependency call</span>
              </div>
            </section>
          </div>
        </article>
      </div>
    </section>
  );
}

function PlaceholderPage({ page }: { page: PageKey }) {
  const title = page.charAt(0).toUpperCase() + page.slice(1);

  return (
    <section className="page-stack">
      <article className="panel placeholder-panel">
        <p className="section-kicker">Static shell</p>
        <h2>{title}</h2>
        <p>This page is reserved for the next frontend screen. No API is connected yet.</p>
      </article>
    </section>
  );
}
