import {
  Activity, AlertTriangle, Bot, Boxes, Braces, ChevronDown, ChevronRight,
  CircleDot, FileCode2, FolderGit2, GitBranch, LayoutDashboard, Network,
  Paperclip, PlugZap, Send, SearchCode, UserRound,
  File, Folder, AlertCircle, Clock, X, Github
} from 'lucide-react';
import { useEffect, useState, useRef } from 'react';
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
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);

// --- 新增 Agent 聊天状态与 RCA 逻辑 ---
  type Message = { id: string; role: 'agent' | 'user'; text: string };
  const [chatMessages, setMessages] = useState<Message[]>([
    {
      id: 'msg-1',
      role: 'agent',
      text: 'Open an endpoint, graph node, or incident, then ask a question. I will use that context when the backend graph is connected.'
    }
  ]);
  const [chatInput, setChatInput] = useState('');
  const chatScrollRef = useRef<HTMLDivElement>(null);
  
  // --- 新增：处理附件上传的逻辑 ---
  const attachmentInputRef = useRef<HTMLInputElement>(null);

  const handleAttachmentClick = () => {
    attachmentInputRef.current?.click();
  };

  const handleAttachmentChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const fileName = files[0].name;
      // 将选中的文件名作为提示，追加到输入框中
      setChatInput((prev) => prev + (prev ? ' ' : '') + `[Attachment: ${fileName}] `);
    }
    // 清空 input 的值，保证用户下次选同一个文件依然能触发
    if (e.target) {
      e.target.value = '';
    }
  };

useEffect(() => {
    if (chatScrollRef.current) {
      // 现在的逻辑：当有新消息时，平滑滚动让整个聊天区域的底部进入视口
      chatScrollRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [chatMessages]);

  // --- 新增：提取出通用的发送消息函数 ---
  const sendMessage = (text: string) => {
    if (!text.trim()) return;

    const newUserMsg: Message = { id: Date.now().toString(), role: 'user', text };
    setMessages((prev) => [...prev, newUserMsg]);

    // 模拟后端 AI 思考延迟
    setTimeout(() => {
      const newAgentMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'agent',
        text: `[模拟响应] 我已接收到指令："${text}"。在真实联调时，我将结合左侧的上下文（端点、代码图谱）为您深度解答。`
      };
      setMessages((prev) => [...prev, newAgentMsg]);
    }, 800);
  };

  // 给底部的输入框表单使用的提交事件
  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(chatInput);
    setChatInput('');
  };

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

useEffect(() => {
  if (isAgentOpen) {
    // 当边栏打开，锁住主页面的滚动条
    document.body.style.overflow = 'hidden';
  } else {
    // 当边栏关闭，恢复主页面的滚动
    document.body.style.overflow = 'auto';
  }
  // 组件卸载时恢复，防止页面卡死
  return () => {
    document.body.style.overflow = 'auto';
  };
}, [isAgentOpen]);

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
       <button className="user-menu" aria-label="Open user menu" onClick={() => setIsLoginModalOpen(true)}>
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
            onReset={() => {
              setIsOnboardingComplete(false);
              setLocalProjectPath('D:\\Hackathon\\LegacyPilot');
            }}
          />
        )}
        {activePage === 'endpoints' && <EndpointsPage onOpenAgent={() => setIsAgentOpen(true)} />}
        {activePage === 'repository' && <RepositoryPage />}
        {activePage === 'graph' && <GraphPage />}
        {activePage === 'incidents' && <IncidentsPage />}
        {['overview', 'onboarding', 'endpoints', 'repository', 'graph', 'incidents'].indexOf(activePage) === -1 && (
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
          <button onClick={() => sendMessage('Find possible failure points')}>
            Find possible failure points
          </button>
          <button onClick={() => sendMessage('Show impact scope')}>
            Show impact scope
          </button>
          <button onClick={() => sendMessage('Generate a maintenance checklist')}>
            Generate a maintenance checklist
          </button>
        </section>

        <div className="agent-chat" ref={chatScrollRef}>
          {chatMessages.map((msg) => (
            <div className={`agent-message ${msg.role === 'user' ? 'user-message' : ''}`} key={msg.id}>
              <strong>{msg.role === 'agent' ? 'LegacyPilot Agent' : 'You'}</strong>
              <p>{msg.text}</p>
            </div>
          ))}
        </div>

<form className="agent-composer" onSubmit={handleSendMessage}>
          {/* --- 新增的隐藏文件选择器 --- */}
          <input
            type="file"
            ref={attachmentInputRef}
            style={{ display: 'none' }}
            onChange={handleAttachmentChange}
          />
          {/* 绑定点击事件 handleAttachmentClick */}
          <button type="button" aria-label="Attach evidence" onClick={handleAttachmentClick}>
            <Paperclip size={18} />
          </button>
          
          <input 
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            placeholder="Ask about this project or incident..." 
            aria-label="Ask the agent" 
          />
          <button type="submit" aria-label="Send message" disabled={!chatInput.trim()}>
            <Send size={18} />
          </button>
        </form>
      </aside>
     {/* --- 新增的登录弹窗 --- */}
      {isLoginModalOpen && (
        <div className="modal-overlay" onClick={() => setIsLoginModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Sign in to LegacyPilot</h3>
              <button className="modal-close" onClick={() => setIsLoginModalOpen(false)}>
                <X size={20} />
              </button>
            </div>
            
            <div className="modal-body">
              <div className="login-provider-group">
                <button className="provider-btn github-btn">
                  <Github size={18} />
                  Continue with GitHub
                </button>
                <button className="provider-btn google-btn">
                  <svg viewBox="0 0 24 24" width="18" height="18" xmlns="http://www.w3.org/2000/svg">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                  </svg>
                  Continue with Google
                </button>
              </div>
              
              <div className="login-divider">
                <span>or sign in with email</span>
              </div>

              <form className="login-form" onSubmit={(e) => { e.preventDefault(); setIsLoginModalOpen(false); }}>
                <div className="form-group">
                  <label htmlFor="email">Email address</label>
                  <input type="email" id="email" placeholder="you@example.com" required />
                </div>
                <div className="form-group">
                  <label htmlFor="password">Password</label>
                  <input type="password" id="password" placeholder="••••••••" required />
                </div>
                <button type="submit" className="primary-action full-width">
                  Sign In
                </button>
              </form>
            </div>
          </div>
        </div>
      )} 
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
  onNavigate,
  onReset
}: {
  isComplete: boolean;
  localPath: string;
  onComplete: () => void;
  onLocalPathChange: (path: string) => void;
  onNavigate: (page: PageKey) => void;
  onReset: () => void;
}) {
  const steps = [
    'Validate local path',
    'Read Git metadata',
    'Scan Java and config files',
    'Extract Spring endpoints',
    'Prepare code graph summary'
  ];

  // --- 新增：用于触发本地文件管理器的 Ref 和处理函数 ---
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleBrowseClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      // 浏览器出于安全限制，无法获取用户电脑真实的绝对路径（会显示 C:\fakepath\...）
      // 这里为了展示效果，提取文件名并拼接到一个虚拟的本地工作区路径中
      const fileName = files[0].name;
      onLocalPathChange(`D:\\Workspace\\${fileName}`);
    }
    // 清空 input value，确保下次选择同一个文件依然能触发 onChange
    if (e.target) {
      e.target.value = ''; 
    }
  };

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
        <div className="page-actions">
          <button className="secondary-action" onClick={onReset}>
            Reset demo
          </button>
          {/* 这里已经删除了原来的 Back to Home 按钮 */}
        </div>
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
            {/* --- 新增：隐藏的系统文件选择器 --- */}
            {/* 注：如果希望只能选择文件夹，可以在下方补充属性 webkitdirectory="" */}
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
            <button className="secondary-action" type="button" onClick={handleBrowseClick}>
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

// 1. 在参数里接收 onOpenAgent
function EndpointsPage({ onOpenAgent }: { onOpenAgent?: () => void }) {
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint>(sampleEndpoints[0]);

  return (
    <section className="page-stack">
      <div className="page-title-row">
        <div>
          <p className="section-kicker">Project / Endpoints</p>
          <h2>Endpoint Analysis</h2>
          {/* ... */}
        </div>
        
        {/* 2. 给按钮绑定 onClick 事件 */}
        <button className="secondary-action" onClick={onOpenAgent}>
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
function RepositoryPage() {
  const mockFiles = [
    { name: 'src/main/java/com/legacypilot/controller', type: 'folder' },
    { name: 'src/main/java/com/legacypilot/service', type: 'folder' },
    { name: 'src/main/resources/application.yml', type: 'file' },
    { name: 'pom.xml', type: 'file' },
  ];

  return (
    <section className="page-stack">
      <div className="page-title-row">
        <div>
          <p className="section-kicker">Project / Repository</p>
          <h2>Source Files</h2>
          <p>Explore the indexed files and their detected knowledge nodes.</p>
        </div>
      </div>
      <article className="panel">
        <div className="panel-header">
          <div>
            <p className="section-kicker">File Tree</p>
            <h3>Project Structure</h3>
          </div>
        </div>
        <div className="workflow-list">
          {mockFiles.map((f, i) => (
            <div className="workflow-item" key={i} style={{ gridTemplateColumns: '32px minmax(0, 1fr)', padding: '10px' }}>
              <div className="workflow-icon" style={{ width: 32, height: 32, background: 'transparent' }}>
                {f.type === 'folder' ? <Folder size={18} color="#1f686d" /> : <File size={18} color="#65757f" />}
              </div>
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <strong style={{ fontSize: '14px', color: '#22323b' }}>{f.name}</strong>
              </div>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}

function GraphPage() {
  return (
    <section className="page-stack">
      <div className="page-title-row">
        <div>
          <p className="section-kicker">Project / Code Graph</p>
          <h2>Knowledge Graph</h2>
          <p>Visual representation of controllers, services, repositories, and their relationships.</p>
        </div>
      </div>
      <article className="panel empty-panel" style={{ minHeight: '400px', alignItems: 'center', textAlign: 'center' }}>
        <div className="empty-icon" style={{ background: '#e9f5f5', color: '#1f686d' }}>
          <Network size={34} />
        </div>
        <h3>Graph Visualization Standby</h3>
        <p style={{ maxWidth: '400px', margin: '10px auto' }}>
          Connects to /v1/graph/query. In a full environment, this area renders a Force-directed graph showing the call chains.
        </p>
      </article>
    </section>
  );
}

function IncidentsPage() {
  // 1. 将原本写死的数组改为 useState 状态管理，以便我们能动态添加数据
  const [incidents, setIncidents] = useState([
    { id: 'INC-092', title: 'NullPointerException in OrderService', status: 'Open', risk: 'High', time: '2 hours ago' },
    { id: 'INC-091', title: 'Database connection timeout', status: 'Resolved', risk: 'Medium', time: '1 day ago' }
  ]);
  
  // 2. 新增一个状态，用来控制按钮的“加载中”效果
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 3. 模拟 Submit Alert 的核心处理流程
  const handleSubmitAlert = () => {
    setIsSubmitting(true); // 按钮变成处理中状态

    // 模拟网络请求和 AI 分析的延迟 (1.5秒)
    setTimeout(() => {
      const mockNewIncident = {
        id: 'INC-093', // 模拟生成的新警报编号
        title: 'OutOfMemoryError: Java heap space in DataExportService', // 模拟一个典型的祖传代码报错
        status: 'Open',
        risk: 'High',
        time: 'Just now'
      };
      
      // 将新警报插入到列表的最前面
      setIncidents(prev => [mockNewIncident, ...prev]);
      setIsSubmitting(false); // 恢复按钮状态
    }, 1500);
  };

  return (
    <section className="page-stack">
      <div className="page-title-row">
        <div>
          <p className="section-kicker">Project / Incidents</p>
          <h2>Incident Analysis</h2>
          <p>Submit Alert -&gt; Build Evidence -&gt; Generate RCA. Trace runtime errors back to legacy code.</p>
        </div>
        {/* 4. 绑定点击事件，并根据 isSubmitting 状态改变文字和透明度 */}
        <button 
          className="primary-action" 
          onClick={handleSubmitAlert}
          disabled={isSubmitting}
          style={{ 
            opacity: isSubmitting ? 0.7 : 1, 
            cursor: isSubmitting ? 'wait' : 'pointer' 
          }}
        >
          {isSubmitting ? 'Analyzing...' : 'Submit Alert'}
        </button>
      </div>
      <div className="endpoint-table">
        {incidents.map(inc => (
          <div className="endpoint-row" key={inc.id} style={{ gridTemplateColumns: '80px minmax(0, 1fr) 100px 120px' }}>
            <span className={`method-badge ${inc.status === 'Open' ? 'method-post' : 'method-get'}`}>
              {inc.status}
            </span>
            <div>
              <strong style={{ display: 'block', color: '#22323b', fontSize: '14px' }}>{inc.title}</strong>
              <span style={{ color: '#65757f', fontSize: '12px' }}>{inc.id}</span>
            </div>
            <span style={{ color: inc.risk === 'High' ? '#d93025' : '#f4b400', fontWeight: 600, fontSize: '13px' }}>
              <AlertCircle size={14} style={{ verticalAlign: 'middle', marginRight: '4px' }}/> 
              {inc.risk}
            </span>
            <span style={{ color: '#71818b', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Clock size={14} /> {inc.time}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}