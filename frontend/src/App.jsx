import { useState } from "react";
import Overview from "./pages/Overview.jsx";
import LiveMonitoring from "./pages/LiveMonitoring.jsx";
import Executions from "./pages/Executions.jsx";
import TestCases from "./pages/TestCases.jsx";
import Replay from "./pages/Replay.jsx";
import FailureAnalysis from "./pages/FailureAnalysis.jsx";
import History from "./pages/History.jsx";
import CITesting from "./pages/CITesting.jsx";

const NAV = [
  ["overview", "Overview"],
  ["monitoring", "Live Agent Monitoring"],
  ["ci", "CI/CD Testing"],
  ["executions", "Agent Executions"],
  ["tests", "Test Cases"],
  ["replay", "Replay Engine"],
  ["failures", "Failure Analysis"],
  ["history", "Test History"],
];

export default function App() {
  const [tab, setTab] = useState("overview");
  const [sel, setSelState] = useState({ testId: null, runId: null }); // shared by Replay Engine
  const setSel = (testId, runId) => setSelState({ testId, runId });
  const openReplay = (testId, runId) => { setSel(testId, runId); setTab("replay"); };

  // Pages remount when you switch tabs, so each one reloads fresh data from the backend.
  const pages = {
    overview: <Overview goTo={setTab} />,
    monitoring: <LiveMonitoring goTo={setTab} />,
    ci: <CITesting />,
    executions: <Executions goTo={setTab} />,
    tests: <TestCases goTo={setTab} openReplay={openReplay} />,
    replay: <Replay testId={sel.testId} runId={sel.runId} setSel={setSel} />,
    failures: <FailureAnalysis openReplay={openReplay} />,
    history: <History />,
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 md:flex">
      <aside className="border-b border-slate-800 bg-slate-900 md:min-h-screen md:w-60 md:border-b-0 md:border-r">
        <div className="px-4 py-4 text-lg font-bold text-slate-100">AgentReliability <span className="text-indigo-400">AI</span></div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-3 md:flex-col md:pb-0">
          {NAV.map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm font-medium ${tab === key ? "bg-indigo-500/20 text-indigo-300" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"}`}>
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">{pages[tab]}</main>
    </div>
  );
}
