import { useState } from "react";
import { register } from "../../api.js";
import { Button, ErrorBox } from "../../ui.jsx";

export default function Register({ onAuthSuccess, onNavigate, systemInfo }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const isCloud = typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1";
  const isPostgres = systemInfo?.database_engine === "postgres" || isCloud;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !password) {
      setError(new Error("All fields are required."));
      return;
    }
    if (password.length < 8) {
      setError(new Error("Password must be at least 8 characters long."));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const user = await register({
        name: name.trim(),
        email: email.trim(),
        password,
      });
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
          <h2 className="mt-3 text-xl font-semibold text-slate-200">Create developer account</h2>
          <p className="mt-1 text-xs text-slate-400">
            Start testing, tracing, and monitoring your agents in CI/CD
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
              {systemInfo?.database_name || (isPostgres ? "Neon PostgreSQL" : "agentreliability.db")}
            </span>
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-400">
            <span>{isCloud ? "Environment:" : "Local Instance:"}</span>
            <span className="font-mono text-slate-300">
              {isCloud ? "Cloud Production" : (systemInfo?.instance_id || "ar_inst_local")}
            </span>
          </div>
          <div className="text-[10px] text-slate-500 truncate" title={systemInfo?.database_path}>
            Storage: {isPostgres ? "Persistent Managed PostgreSQL (Neon)" : (systemInfo?.database_path || "backend/agentreliability.db")}
          </div>
        </div>

        {error && <ErrorBox error={error} />}

        {/* Project Creation Explanation (Requirement 5 & 9) */}
        <div className="rounded-xl border border-indigo-500/20 bg-indigo-950/20 p-3 text-xs text-indigo-300/90 space-y-1">
          <div className="flex items-center gap-1.5 font-semibold text-indigo-200">
            <svg className="h-4 w-4 shrink-0 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>Starter Project Policy:</span>
          </div>
          <p className="text-[11px] leading-relaxed text-slate-300">
            A starter project is <strong>not</strong> automatically created upon registration. After signing in, you will be able to create a custom project with your own name or explore using the one-click demo.
          </p>
        </div>

        <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="block text-xs font-medium text-slate-300">Full Name</label>
            <input
              type="text"
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ada Lovelace"
              className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300">Email Address</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="developer@company.com"
              className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <p className="mt-1 text-xs text-slate-500">Minimum 8 characters (scrypt hash stored locally)</p>
          </div>

          <Button
            type="submit"
            disabled={loading}
            className="w-full justify-center py-2.5 text-center text-sm font-semibold"
          >
            {loading ? "Creating account…" : "Create Developer Account"}
          </Button>
        </form>

        <div className="mt-4 border-t border-slate-800 pt-3 text-center text-xs text-slate-400">
          Already registered in this database?{" "}
          <button
            onClick={() => onNavigate("login")}
            className="font-medium text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            Sign in
          </button>
        </div>
      </div>
    </div>
  );
}

