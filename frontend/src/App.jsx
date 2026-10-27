import { useState, useEffect, useCallback, useMemo } from "react";
import Overview from "./pages/Overview.jsx";
import LiveMonitoring from "./pages/LiveMonitoring.jsx";
import Executions from "./pages/Executions.jsx";
import TestCases from "./pages/TestCases.jsx";
import Replay from "./pages/Replay.jsx";
import FailureAnalysis from "./pages/FailureAnalysis.jsx";
import History from "./pages/History.jsx";
import CITesting from "./pages/CITesting.jsx";
import ApiKeys from "./pages/ApiKeys.jsx";
import RegressionTesting from "./pages/RegressionTesting.jsx";
import GettingStarted from "./pages/GettingStarted.jsx";
import HelpDocs from "./pages/HelpDocs.jsx";
import ProjectSwitcher from "./components/ProjectSwitcher.jsx";
import Login from "./pages/auth/Login.jsx";
import Register from "./pages/auth/Register.jsx";
import ForgotPassword from "./pages/auth/ForgotPassword.jsx";
import ResetPassword from "./pages/auth/ResetPassword.jsx";
import DemoBanner from "./components/DemoBanner.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import { isDemoMode } from "./demo/isDemoMode.js";
import { getMe, listProjects, createProject, logout, setActiveProjectId, getSystemInfo, seedDemoData } from "./api.js";
import { Button } from "./ui.jsx";

// Structured primary navigation sections
export const NAV_SECTIONS = [
  {
    title: "Overview",
    items: [
      {
        key: "overview",
        label: "Overview",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        ),
      },
      {
        key: "getting-started",
        label: "Getting Started",
        badge: "Guide",
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: "Traces & Observability",
    items: [
      {
        key: "monitoring",
        label: "Live Monitoring",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
      },
      {
        key: "executions",
        label: "Agent Executions",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        key: "history",
        label: "Test History",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: "Regressions & Baselines",
    items: [
      {
        key: "regression",
        label: "Golden Baselines",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      },
      {
        key: "tests",
        label: "Test Cases",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
        ),
      },
      {
        key: "ci",
        label: "CI/CD Testing",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        ),
      },
      {
        key: "replay",
        label: "Replay Engine",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: "Diagnostics & Root Cause",
    items: [
      {
        key: "failures",
        label: "Failure Analysis",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: "Configuration",
    items: [
      {
        key: "apikeys",
        label: "API Keys & SDK",
        badge: null,
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: "Help & Resources",
    items: [
      {
        key: "docs",
        label: "Help & Documentation",
        badge: "Docs",
        icon: (
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        ),
      },
    ],
  },
];

const VALID_TAB_KEYS = NAV_SECTIONS.flatMap((s) => s.items.map((i) => i.key));

function NavigationMenu({
  tab,
  setTab,
  onNavigate,
  user,
  onLogout,
  projects,
  currentProject,
  onSelectProject,
  fetchProjects,
  setNewKeyNotification,
  systemInfo,
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Brand Header */}
      <div className="border-b border-slate-800 px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-slate-100 tracking-tight">AgentReliability</span>
          <span className="rounded bg-indigo-500/20 px-1.5 py-0.5 text-[11px] font-bold text-indigo-400 border border-indigo-500/30">
            AI
          </span>
        </div>
        <div className="text-[10px] text-slate-400 font-medium mt-0.5">
          Agent QA & Regression Engine
        </div>
      </div>

      {/* Project Switcher */}
      <div className="border-b border-slate-800/80 bg-slate-950/40">
        <ProjectSwitcher
          projects={projects}
          currentProject={currentProject}
          onSelectProject={onSelectProject}
          onProjectsUpdated={fetchProjects}
          onKeyGenerated={(info) => setNewKeyNotification(info)}
        />
      </div>

      {/* Structured Sections */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title} className="space-y-1">
            <div className="px-2.5 text-[10px] font-semibold tracking-wider text-slate-500 uppercase">
              {section.title}
            </div>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const isActive = tab === item.key;
                return (
                  <button
                    key={item.key}
                    onClick={() => onNavigate(item.key)}
                    className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs font-medium transition ${
                      isActive
                        ? "bg-indigo-600/15 text-indigo-300 font-semibold ring-1 ring-indigo-500/30 border-l-2 border-indigo-400 pl-2"
                        : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                    }`}
                  >
                    <div className="flex items-center gap-2.5 truncate">
                      <span
                        className={
                          isActive ? "text-indigo-400" : "text-slate-500 group-hover:text-slate-300"
                        }
                      >
                        {item.icon}
                      </span>
                      <span className="truncate">{item.label}</span>
                    </div>
                    {item.badge && (
                      <span className="rounded bg-indigo-500/20 px-1.5 py-0.5 text-[9px] font-semibold text-indigo-300 border border-indigo-500/30">
                        {item.badge}
                      </span>
                    )}
                    {isActive && !item.badge && (
                      <span className="h-1.5 w-1.5 rounded-full bg-indigo-400"></span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Database & Instance Status */}
      <div className="border-t border-slate-800/60 px-3 py-2 bg-slate-950/20">
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <div className="flex items-center gap-1.5 truncate">
            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${isDemoMode() ? "bg-indigo-400" : "bg-emerald-400"}`}></span>
            <span className="truncate font-medium text-slate-300">
              {isDemoMode()
                ? "Public Demo Store"
                : (systemInfo?.database_name || (systemInfo?.database_engine === "postgres" ? "Neon PostgreSQL" : "SQLite Database"))}
            </span>
          </div>
          <span
            title={systemInfo?.database_path || "Database"}
            className="rounded bg-slate-800/80 px-1.5 py-0.5 text-[9px] font-mono text-slate-400 border border-slate-700/50 shrink-0"
          >
            {isDemoMode()
              ? "demo"
              : (systemInfo?.database_engine === "postgres" ? "postgres" : (systemInfo?.instance_id ? systemInfo.instance_id.slice(0, 15) : "local"))}
          </span>
        </div>
      </div>

      {/* User Profile & Sign Out Footer */}
      <div className="border-t border-slate-800 p-3 bg-slate-950/40">
        <div className="flex items-center justify-between gap-2">
          <div className="truncate">
            <div className="truncate text-xs font-semibold text-slate-200 flex items-center gap-1.5">
              <span>{user?.name}</span>
              {isDemoMode() && (
                <span className="rounded bg-indigo-500/20 px-1 py-0.5 text-[9px] font-medium text-indigo-300 border border-indigo-500/40">
                  Demo
                </span>
              )}
            </div>
            <div className="truncate text-[11px] text-slate-500">{user?.email}</div>
          </div>
          <button
            onClick={onLogout}
            title={isDemoMode() ? "Reset demo state" : "Sign out"}
            className="flex-shrink-0 rounded-lg p-1.5 text-xs text-slate-400 hover:bg-slate-800 hover:text-red-400 transition"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

function getStoredProjectId(instanceId, userId) {
  if (!userId || typeof window === "undefined") return null;
  try {
    const key = `agentreliability_project_${instanceId || "default"}_${userId}`;
    const val = localStorage.getItem(key) || localStorage.getItem(`agentreliability_project_${userId}`);
    return val ? parseInt(val, 10) : null;
  } catch {
    return null;
  }
}

function setStoredProjectId(instanceId, userId, projId) {
  if (!userId || typeof window === "undefined") return;
  try {
    const key = `agentreliability_project_${instanceId || "default"}_${userId}`;
    if (projId) {
      localStorage.setItem(key, String(projId));
      localStorage.setItem(`agentreliability_project_${userId}`, String(projId));
    } else {
      localStorage.removeItem(key);
      localStorage.removeItem(`agentreliability_project_${userId}`);
    }
  } catch {
    // Ignore storage errors in restricted contexts
  }
}

function EmptyProjectState({
  user,
  systemInfo,
  onCreateProject,
  onLoadDemo,
  seedingDemo,
}) {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);

  async function handleCreate(e) {
    e.preventDefault();
    if (!projectName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      await onCreateProject(projectName.trim());
      setShowCreateForm(false);
      setProjectName("");
    } catch (err) {
      setCreateError(err?.message || "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl py-12 px-4 text-center">
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600/20 text-indigo-400 ring-1 ring-indigo-500/30">
          <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>

        <h2 className="mt-4 text-xl font-bold text-slate-100">
          Welcome to AgentReliability AI, {user?.name || "Developer"}!
        </h2>
        <p className="mt-2 text-xs text-slate-400 max-w-lg mx-auto leading-relaxed">
          Your account currently has no active projects in this connected local database. Projects provide multi-tenant isolation for your agent traces, Golden Baselines, test suites, and API keys.
        </p>

        {showCreateForm ? (
          <form onSubmit={handleCreate} className="mt-6 max-w-md mx-auto space-y-3 text-left">
            {createError && (
              <div className="p-2.5 rounded-lg bg-red-950/30 border border-red-500/40 text-xs text-red-300">
                {createError}
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold text-slate-300">Project Name</label>
              <input
                type="text"
                required
                autoFocus
                placeholder="e.g. Customer Support AI, Research Agent"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Button type="submit" disabled={creating} className="flex-1 justify-center py-2 text-sm font-semibold">
                {creating ? "Creating Project…" : "Create Project"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setShowCreateForm(false)}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Button
              onClick={() => setShowCreateForm(true)}
              className="w-full sm:w-auto px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 font-semibold"
            >
              + Create Your First Project
            </Button>
            <Button
              variant="secondary"
              onClick={onLoadDemo}
              disabled={seedingDemo}
              className="w-full sm:w-auto px-5 py-2.5"
            >
              {seedingDemo ? "Loading Demo…" : "🚀 Load One-Click Demo Project"}
            </Button>
          </div>
        )}

        {/* Connected Database Info Card (Requirements 8 & 9) */}
        <div className="mt-8 rounded-xl border border-slate-800 bg-slate-950/80 p-4 text-left text-xs space-y-2">
          <div className="flex items-center justify-between text-slate-300 font-medium">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
              {systemInfo?.database_engine === "postgres" ? "Connected Database:" : "Connected Local Database:"}
            </span>
            <code className="text-emerald-400 font-mono text-[11px]">{systemInfo?.database_name || (systemInfo?.database_engine === "postgres" ? "Neon PostgreSQL" : "agentreliability.db")}</code>
          </div>
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>{systemInfo?.database_engine === "postgres" ? "Deployment:" : "Instance Identifier:"}</span>
            <code className="text-indigo-300 font-mono">{systemInfo?.database_engine === "postgres" ? "Cloud Production" : (systemInfo?.instance_id || "ar_inst_local")}</code>
          </div>
          <div className="text-[10px] text-slate-500 truncate" title={systemInfo?.database_path}>
            Storage: {systemInfo?.database_path || (systemInfo?.database_engine === "postgres" ? "Persistent Managed PostgreSQL (Neon)" : "backend/agentreliability.db")}
          </div>
          {systemInfo?.database_engine !== "postgres" ? (
            <>
              <p className="text-[11px] text-slate-400 pt-1.5 border-t border-slate-800/80 leading-relaxed">
                <strong>Local Isolation Policy:</strong> AgentReliability stores accounts, projects, baselines, and traces in your current installation's local SQLite database. Independent local installations (e.g. running on different ports or extracted in separate folders) maintain completely isolated databases and <strong>do not synchronize accounts or projects based on email alone</strong>.
              </p>
              <p className="text-[10px] text-slate-500">
                If you created projects in another installation, import them using:
                <code className="block mt-1 text-slate-300 bg-slate-900 p-1.5 rounded font-mono text-[10px]">
                  agentreliability import-db --source &lt;path-to-other-agentreliability.db&gt;
                </code>
              </p>
            </>
          ) : (
            <p className="text-[11px] text-slate-400 pt-1.5 border-t border-slate-800/80 leading-relaxed">
              <strong>Cloud Persistence:</strong> Your projects, test runs, Golden Baselines, and traces are securely persisted in Neon PostgreSQL.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [initError, setInitError] = useState(null);
  const [authScreen, setAuthScreen] = useState("login"); // 'login' | 'register' | 'forgot-password' | 'reset-password'
  const [resetToken, setResetToken] = useState("");
  const [systemInfo, setSystemInfo] = useState(null);

  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState(null);
  const [newKeyNotification, setNewKeyNotification] = useState(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [seedingDemoState, setSeedingDemoState] = useState(false);

  // Fetch local instance & system information
  useEffect(() => {
    getSystemInfo().then(setSystemInfo).catch(() => {});
  }, []);

  // Initialize active tab from URL hash if valid, defaulting to "overview"
  const [tab, setTab] = useState(() => {
    if (typeof window !== "undefined" && window.location.hash) {
      const hashKey = window.location.hash.replace(/^#\/?/, "").toLowerCase();
      if (VALID_TAB_KEYS.includes(hashKey)) {
        return hashKey;
      }
    }
    return "overview";
  });

  const [sel, setSelState] = useState({ testId: null, runId: null });
  const setSel = (testId, runId) => setSelState({ testId, runId });
  const openReplay = (testId, runId) => {
    setSel(testId, runId);
    setTab("replay");
  };

  // Sync hash changes (browser back/forward or external deep links)
  useEffect(() => {
    function handleHashChange() {
      const hashKey = window.location.hash.replace(/^#\/?/, "").toLowerCase();
      if (VALID_TAB_KEYS.includes(hashKey)) {
        setTab(hashKey);
      }
    }
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  // Update URL hash when tab changes
  useEffect(() => {
    if (typeof window !== "undefined") {
      const currentHash = window.location.hash.replace(/^#\/?/, "").toLowerCase();
      if (currentHash !== tab) {
        window.history.replaceState(null, "", `#${tab}`);
      }
    }
  }, [tab]);

  // Map of tab keys to readable labels
  const currentNavLabel = useMemo(() => {
    for (const section of NAV_SECTIONS) {
      const found = section.items.find((i) => i.key === tab);
      if (found) return found.label;
    }
    return "Overview";
  }, [tab]);

  // Fetch projects and set active project with persistence
  const fetchProjects = useCallback(async (activeUser = user, activeInstanceId = systemInfo?.instance_id) => {
    try {
      const projs = await listProjects();
      setProjects(projs);
      if (projs.length > 0) {
        const uid = activeUser?.id;
        const storedId = getStoredProjectId(activeInstanceId, uid);
        const storedMatch = storedId ? projs.find((p) => p.id === storedId) : null;
        setCurrentProject((prev) => {
          const prevMatch = prev ? projs.find((p) => p.id === prev.id) : null;
          const selected = storedMatch || prevMatch || projs[0];
          setActiveProjectId(selected.id);
          if (uid) setStoredProjectId(activeInstanceId, uid, selected.id);
          return selected;
        });
      } else {
        setCurrentProject(null);
        setActiveProjectId(null);
      }
      return projs;
    } catch {
      return [];
    }
  }, [user, systemInfo?.instance_id]);

  // Initialize session on mount
  useEffect(() => {
    let mounted = true;
    getMe()
      .then(async (u) => {
        if (!mounted) return;
        setInitError(null);
        const sys = await getSystemInfo().catch(() => null);
        if (sys) setSystemInfo(sys);
        setUser(u);
        await fetchProjects(u, sys?.instance_id);
      })
      .catch((err) => {
        if (!mounted) return;
        setUser(null);
        if (err?.isTimeout || err?.isNetworkError) {
          setInitError(err);
        }
      })
      .finally(() => {
        if (mounted) setAuthLoading(false);
      });

    // Handle 401 events dispatched from api.js
    function handleUnauthorized() {
      if (isDemoMode()) return; // Never show login screen in demo mode
      setUser(null);
      setActiveProjectId(null);
      setAuthScreen("login");
    }

    window.addEventListener("agentreliability:unauthorized", handleUnauthorized);
    return () => {
      mounted = false;
      window.removeEventListener("agentreliability:unauthorized", handleUnauthorized);
    };
  }, [fetchProjects]);

  async function handleAuthSuccess(userData) {
    setAuthLoading(true);
    try {
      const projs = await listProjects();
      setProjects(projs);
      if (projs.length > 0) {
        const storedId = getStoredProjectId(systemInfo?.instance_id, userData.id);
        const storedMatch = storedId ? projs.find((p) => p.id === storedId) : null;
        const selected = storedMatch || projs[0];
        setCurrentProject(selected);
        setActiveProjectId(selected.id);
        setStoredProjectId(systemInfo?.instance_id, userData.id, selected.id);
      } else {
        setCurrentProject(null);
        setActiveProjectId(null);
      }
      setUser(userData);
      setTab("overview");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Proceed with local logout regardless of network response
    }
    if (isDemoMode()) {
      // In demo mode, reset to initial demo state
      const u = await getMe();
      setUser(u);
      const projs = await fetchProjects(u);
      if (projs.length > 0) handleSelectProject(projs[0]);
      setTab("overview");
      return;
    }
    setUser(null);
    setActiveProjectId(null);
    setCurrentProject(null);
    setProjects([]);
    setAuthScreen("login");
  }

  function handleSelectProject(proj) {
    setCurrentProject(proj);
    setActiveProjectId(proj?.id || null);
    if (user?.id && proj?.id) {
      setStoredProjectId(systemInfo?.instance_id, user.id, proj.id);
    }
  }

  async function handleCreateProjectFromEmptyState(name) {
    const res = await createProject({ name });
    const projs = await fetchProjects(user);
    if (res?.id) {
      const match = projs.find((p) => p.id === res.id);
      if (match) {
        handleSelectProject(match);
      }
    }
    if (res?.api_key) {
      setNewKeyNotification({ key: res.api_key, projectName: res.name });
    }
    setTab("overview");
  }

  async function handleSeedDemoForEmptyState() {
    setSeedingDemoState(true);
    try {
      const demoRes = await seedDemoData();
      const projs = await fetchProjects(user);
      if (demoRes?.project_id) {
        const match = projs.find((p) => p.id === demoRes.project_id);
        if (match) {
          handleSelectProject(match);
        }
      }
      setTab("overview");
    } finally {
      setSeedingDemoState(false);
    }
  }

  // Loading state
  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent"></div>
          <span className="text-xs font-medium">Connecting to AgentReliability AI…</span>
        </div>
      </div>
    );
  }

  // Unauthenticated flow
  if (!user) {
    if (authScreen === "register") {
      return (
        <Register
          onAuthSuccess={handleAuthSuccess}
          onNavigate={setAuthScreen}
          systemInfo={systemInfo}
        />
      );
    }
    if (authScreen === "forgot-password") {
      return (
        <ForgotPassword
          onNavigate={setAuthScreen}
          onSetResetToken={(token) => setResetToken(token)}
        />
      );
    }
    if (authScreen === "reset-password") {
      return <ResetPassword initialToken={resetToken} onNavigate={setAuthScreen} />;
    }
    return (
      <Login
        onAuthSuccess={handleAuthSuccess}
        onNavigate={setAuthScreen}
        systemInfo={systemInfo}
        initialError={initError}
        onRetry={() => {
          setInitError(null);
          setAuthLoading(true);
          getMe()
            .then(async (u) => {
              const sys = await getSystemInfo().catch(() => null);
              if (sys) setSystemInfo(sys);
              setUser(u);
              await fetchProjects(u, sys?.instance_id);
            })
            .catch((err) => {
              setUser(null);
              if (err?.isTimeout || err?.isNetworkError) {
                setInitError(err);
              }
            })
            .finally(() => setAuthLoading(false));
        }}
      />
    );
  }

  // Dashboard pages (remount when project switches via key={currentProject?.id})
  const pages = {
    overview: <Overview key={currentProject?.id} goTo={setTab} />,
    "getting-started": (
      <GettingStarted
        key={currentProject?.id}
        currentProject={currentProject}
        user={user}
        systemInfo={systemInfo}
        goTo={setTab}
      />
    ),
    monitoring: <LiveMonitoring key={currentProject?.id} goTo={setTab} />,
    regression: <RegressionTesting key={currentProject?.id} goTo={setTab} />,
    ci: <CITesting key={currentProject?.id} />,
    executions: <Executions key={currentProject?.id} goTo={setTab} />,
    tests: <TestCases key={currentProject?.id} goTo={setTab} openReplay={openReplay} />,
    replay: <Replay key={currentProject?.id} testId={sel.testId} runId={sel.runId} setSel={setSel} />,
    failures: <FailureAnalysis key={currentProject?.id} openReplay={openReplay} />,
    history: <History key={currentProject?.id} />,
    apikeys: <ApiKeys key={currentProject?.id} currentProject={currentProject} />,
    docs: <HelpDocs key={currentProject?.id} goTo={setTab} />,
  };

  const isDemo = isDemoMode();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 flex flex-col">
      {isDemo && (
        <DemoBanner
          currentProject={currentProject}
          projects={projects}
          onSelectProject={handleSelectProject}
          onResetDemo={async () => {
            const u = await getMe();
            setUser(u);
            const projs = await fetchProjects(u);
            if (projs.length > 0) handleSelectProject(projs[0]);
            setTab("overview");
          }}
        />
      )}
      <div className="flex-1 md:flex">
        {/* Mobile Top Navigation Bar */}
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-4 py-3 md:hidden sticky top-0 z-30">
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Open navigation menu"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div>
            <div className="text-sm font-bold text-slate-100 flex items-center gap-1">
              <span>AgentReliability</span>
              <span className="text-indigo-400">AI</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded bg-indigo-500/15 px-2 py-0.5 text-xs font-medium text-indigo-300 border border-indigo-500/30">
            {currentNavLabel}
          </span>
        </div>
      </div>

      {/* Mobile Drawer (Visible when mobileMenuOpen is true) */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm"
            onClick={() => setMobileMenuOpen(false)}
          />
          <aside className="relative flex h-full w-72 max-w-[85vw] flex-col border-r border-slate-800 bg-slate-900 shadow-2xl z-10">
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800/80">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Navigation</span>
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 text-xs flex items-center gap-1"
              >
                <span>Close</span>
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <NavigationMenu
              tab={tab}
              setTab={setTab}
              onNavigate={(key) => {
                setTab(key);
                setMobileMenuOpen(false);
              }}
              user={user}
              onLogout={handleLogout}
              projects={projects}
              currentProject={currentProject}
              onSelectProject={handleSelectProject}
              fetchProjects={fetchProjects}
              setNewKeyNotification={setNewKeyNotification}
              systemInfo={systemInfo}
            />
          </aside>
        </div>
      )}

      {/* Desktop Sticky Sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col md:border-r border-slate-800 bg-slate-900 md:min-h-screen shrink-0 sticky top-0 h-screen overflow-hidden">
        <NavigationMenu
          tab={tab}
          setTab={setTab}
          onNavigate={setTab}
          user={user}
          onLogout={handleLogout}
          projects={projects}
          currentProject={currentProject}
          onSelectProject={handleSelectProject}
          fetchProjects={fetchProjects}
          setNewKeyNotification={setNewKeyNotification}
          systemInfo={systemInfo}
        />
      </aside>

      {/* Main Content Area */}
      <main className="min-w-0 flex-1 p-4 md:p-8">
        {/* Initial API Key Notice (if a new project was created with an auto-provisioned key) */}
        {newKeyNotification && (
          <div className="mb-6 rounded-2xl bg-slate-900 p-4 ring-1 ring-emerald-500/50">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-bold text-emerald-400">
                  <span>✓ Project & Initial API Key Created for "{newKeyNotification.projectName}"</span>
                </div>
                <p className="mt-1 text-xs text-slate-300">
                  Save your key now. For your security, this full key will not be shown again:
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="rounded bg-slate-950 px-2.5 py-1 font-mono text-xs text-emerald-300 select-all">
                    {newKeyNotification.key}
                  </code>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      navigator.clipboard.writeText(newKeyNotification.key);
                      setCopiedKey(true);
                      setTimeout(() => setCopiedKey(false), 2000);
                    }}
                    className="text-xs py-1"
                  >
                    {copiedKey ? "✓ Copied!" : "Copy"}
                  </Button>
                </div>
              </div>
              <button
                onClick={() => setNewKeyNotification(null)}
                className="text-slate-400 hover:text-slate-200 text-sm"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {projects.length === 0 ? (
          <EmptyProjectState
            user={user}
            systemInfo={systemInfo}
            onCreateProject={handleCreateProjectFromEmptyState}
            onLoadDemo={handleSeedDemoForEmptyState}
            seedingDemo={seedingDemoState}
          />
        ) : (
          <ErrorBoundary key={tab} onNavigate={setTab}>
            {pages[tab] || pages.overview}
          </ErrorBoundary>
        )}
      </main>
      </div>
    </div>
  );
}
