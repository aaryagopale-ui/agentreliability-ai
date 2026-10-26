import { useState } from "react";
import { forgotPassword } from "../../api.js";
import { Button, ErrorBox } from "../../ui.jsx";

export default function ForgotPassword({ onNavigate, onSetResetToken }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successInfo, setSuccessInfo] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email.trim()) {
      setError(new Error("Please enter your email address."));
      return;
    }
    setLoading(true);
    setError(null);
    setSuccessInfo(null);
    try {
      const res = await forgotPassword({ email: email.trim() });
      setSuccessInfo(res);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  function handleUseDevToken() {
    if (successInfo?.dev_reset_token) {
      if (onSetResetToken) onSetResetToken(successInfo.dev_reset_token);
      onNavigate("reset-password");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-slate-900 p-8 shadow-2xl ring-1 ring-slate-800">
        <div className="text-center">
          <div className="inline-block text-2xl font-bold tracking-tight text-slate-100">
            AgentReliability <span className="text-indigo-400">AI</span>
          </div>
          <h2 className="mt-4 text-xl font-semibold text-slate-200">Reset your password</h2>
          <p className="mt-1 text-sm text-slate-400">
            Enter your email address and we'll send you instructions
          </p>
        </div>

        {error && <ErrorBox error={error} />}

        {successInfo ? (
          <div className="space-y-4">
            <div className="rounded-xl bg-emerald-500/10 p-4 text-sm text-emerald-300 ring-1 ring-emerald-500/30">
              <p className="font-semibold">{successInfo.message}</p>
              <p className="mt-1 text-xs text-emerald-400">
                Check your inbox for a secure password reset link.
              </p>
            </div>

            {/* Development-only helper pill */}
            {successInfo.dev_reset_token && (
              <div className="rounded-xl bg-amber-500/10 p-4 text-xs text-amber-200 ring-1 ring-amber-500/30">
                <span className="font-bold uppercase tracking-wider text-amber-300">Development Notice:</span>
                <p className="mt-1 font-mono text-[11px] text-amber-100 break-all">
                  {successInfo.dev_reset_token}
                </p>
                <button
                  type="button"
                  onClick={handleUseDevToken}
                  className="mt-3 block w-full rounded-lg bg-amber-500/20 py-1.5 text-center font-semibold text-amber-300 hover:bg-amber-500/30 transition"
                >
                  Proceed with this token →
                </button>
              </div>
            )}

            <Button
              variant="ghost"
              onClick={() => onNavigate("reset-password")}
              className="w-full justify-center py-2 text-center text-sm"
            >
              Enter Reset Token Manually
            </Button>
          </div>
        ) : (
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

            <Button
              type="submit"
              disabled={loading}
              className="w-full justify-center py-2.5 text-center text-sm font-semibold"
            >
              {loading ? "Sending link…" : "Send Reset Link"}
            </Button>
          </form>
        )}

        <div className="mt-6 border-t border-slate-800 pt-4 text-center text-xs text-slate-400">
          Remember your password?{" "}
          <button
            onClick={() => onNavigate("login")}
            className="font-medium text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            Back to sign in
          </button>
        </div>
      </div>
    </div>
  );
}

