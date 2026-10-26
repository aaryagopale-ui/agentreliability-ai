import { useState } from "react";
import { login } from "../../api.js";
import { Button, ErrorBox } from "../../ui.jsx";

export default function Login({ onAuthSuccess, onNavigate, systemInfo, initialError, onRetry }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(initialError || null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError(new Error("Please enter both email and password."));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const user = await login({ email: email.trim(), password });
      onAuthSuccess(user);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-6 rounded-2xl bg-slate-900 p-8 shadow-2xl ring-1 ring-slate-800">
        <div className="text-center">
          <div className="inline-block text-2xl font-bold tracking-tight text-slate-100">
            AgentReliability <span className="text-indigo-400">AI</span>
          </div>
          <h2 className="mt-3 text-xl font-semibold text-slate-200">Sign in to your account</h2>
          <p className="mt-1 text-xs text-slate-400">
            Developer infrastructure for testing & monitoring AI agents
          </p>
        </div>

        {/* Connected Database & Instance Card */}
        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-xs space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-medium text-slate-300">
              <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
              Connected Database:
            </span>
            <span className="font-mono text-[11px] text-emerald-400">
              {systemInfo?.database_name || "agentreliability.db"}
            </span>
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-400">
            <span>Local Instance:</span>
            <span className="font-mono text-slate-300">
              {systemInfo?.instance_id || "ar_inst_local"}
            </span>
          </div>
          <div className="text-[10px] text-slate-500 truncate" title={systemInfo?.database_path}>
            Storage: {systemInfo?.database_path || "backend/agentreliability.db"}
          </div>
        </div>

        {error && (
          <div className="space-y-2.5">
            <ErrorBox error={error} />
            {error.isTimeout ? (
              <div className="rounded-lg border border-amber-500/40 bg-amber-950/30 p-3.5 text-xs text-amber-200 space-y-2">
                <div className="flex items-center gap-2 font-bold text-amber-300">
                  <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse"></span>
                  <span>Backend Unresponsiveness or Timeout</span>
                </div>
                <p className="text-[11px] leading-relaxed text-amber-200/90">
                  The backend service timed out while processing requests. This may occur if a server process hung on pipe I/O or is restarting.
                </p>
                <div className="rounded bg-slate-950/80 p-2 font-mono text-[11px] text-slate-300 border border-slate-800">
                  agentreliability dev
                </div>
                {onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="mt-1 rounded bg-amber-500/20 px-2.5 py-1 text-xs font-semibold text-amber-300 hover:bg-amber-500/30 border border-amber-500/40 transition"
                  >
                    Retry Connection
                  </button>
                )}
              </div>
            ) : error.isNetworkError ? (
              <div className="rounded-lg border border-red-500/40 bg-red-950/30 p-3.5 text-xs text-red-200 space-y-2">
                <div className="flex items-center gap-2 font-bold text-red-300">
                  <span className="h-2 w-2 rounded-full bg-red-400 animate-pulse"></span>
                  <span>Backend Connectivity Issue</span>
                </div>
                <p className="text-[11px] leading-relaxed text-red-300/90">
                  The dashboard could not establish a connection to the AgentReliability backend API.
                </p>
                <div className="rounded bg-slate-950/80 p-2 font-mono text-[11px] text-slate-300 border border-slate-800">
                  agentreliability dev
                </div>
                <p className="text-[10px] text-slate-400">
                  Ensure the command above is actively running in your terminal, or run <code className="text-indigo-300">agentreliability doctor</code> to diagnose.
                </p>
                {onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="mt-1 rounded bg-red-500/20 px-2.5 py-1 text-xs font-semibold text-red-300 hover:bg-red-500/30 border border-red-500/40 transition"
                  >
                    Retry Connection
                  </button>
                )}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-400 space-y-1">
                <div className="flex items-center gap-1.5 font-medium text-slate-300">
                  <svg className="h-4 w-4 text-indigo-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>Working with multiple local installations?</span>
                </div>
                <p className="text-[11px] leading-relaxed text-slate-400">
                  <strong>Important:</strong> Independent local databases do not synchronize accounts based on email alone. If your account was registered in a different folder or port, your credentials exist only in that folder's SQLite database.
                </p>
                <p className="text-[10px] text-slate-500 pt-0.5">
                  Use <code className="text-indigo-300 bg-slate-900 px-1 py-0.5 rounded">agentreliability import-db --source &lt;path&gt;</code> to migrate accounts, or click "Create account" below.
                </p>
              </div>
            )}
          </div>
        )}

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="block text-xs font-medium text-slate-300">Email Address</label>
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="developer@company.com"
              className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="block text-xs font-medium text-slate-300">Password</label>
              <button
                type="button"
                onClick={() => onNavigate("forgot-password")}
                className="text-xs font-medium text-indigo-400 hover:text-indigo-300 hover:underline"
              >
                Forgot password?
              </button>
            </div>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <Button
            type="submit"
            disabled={loading}
            className="w-full justify-center py-2.5 text-center text-sm font-semibold"
          >
            {loading ? "Signing in…" : "Sign In"}
          </Button>
        </form>

        <div className="mt-6 border-t border-slate-800 pt-4 text-center text-xs text-slate-400">
          Don't have an account?{" "}
          <button
            onClick={() => onNavigate("register")}
            className="font-medium text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            Create an account
          </button>
        </div>
      </div>
    </div>
  );
}

