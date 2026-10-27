import { useState } from "react";
import { demoService } from "../demo/demoService.js";

/**
 * Public Demo Mode notification banner with interactive project switching and state reset.
 * Fully mobile responsive.
 */
export default function DemoBanner({ currentProject, onResetDemo, onSelectProject, projects }) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="bg-gradient-to-r from-indigo-900/90 via-purple-900/90 to-slate-900 border-b border-indigo-500/40 px-3 py-2 text-xs text-indigo-100 shadow-md">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2">
        {/* Left: Indicator & Headline */}
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-2 w-2 shrink-0 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-400"></span>
          </span>
          <span className="font-bold tracking-wide uppercase text-[10px] bg-indigo-500/30 text-indigo-200 px-1.5 py-0.5 rounded border border-indigo-400/30 shrink-0">
            Public Demo
          </span>
          <p className="truncate text-slate-200 text-xs">
            <span className="hidden sm:inline">Exploring </span>
            <strong className="text-white">{currentProject?.name || "Customer Support AI"}</strong>
            <span className="hidden md:inline text-indigo-200/80"> — Realistic synthetic data, no login required</span>
          </p>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="text-[11px] text-indigo-300 hover:text-white underline hidden sm:inline"
          >
            {showDetails ? "Hide Info" : "Demo Guide"}
          </button>

          {projects && projects.length > 1 && (
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-indigo-300 hidden lg:inline">Switch Demo:</span>
              <select
                value={currentProject?.id || 1}
                onChange={(e) => {
                  const match = projects.find((p) => p.id === Number(e.target.value));
                  if (match && onSelectProject) onSelectProject(match);
                }}
                className="rounded bg-slate-950/80 px-2 py-0.5 text-xs text-indigo-200 border border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-400"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              demoService.resetState();
              if (onResetDemo) onResetDemo();
            }}
            title="Reset in-memory demo data to initial state"
            className="rounded bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 hover:text-white px-2 py-0.5 text-[11px] font-medium border border-indigo-400/40 transition"
          >
            ↻ Reset Demo
          </button>
        </div>
      </div>

      {/* Expandable Demo Guide Drawer */}
      {showDetails && (
        <div className="mt-2 pt-2 border-t border-indigo-500/20 text-[11px] text-indigo-200/90 leading-relaxed max-w-4xl">
          <p>
            <strong>About this Public Demo:</strong> This environment is completely isolated from production. All traces, Golden Baselines, tests, and AI failure diagnostics are simulated in-memory using deterministic realistic scenarios. To protect security, live API key provisioning and account modifications are disabled.
          </p>
        </div>
      )}
    </div>
  );
}

