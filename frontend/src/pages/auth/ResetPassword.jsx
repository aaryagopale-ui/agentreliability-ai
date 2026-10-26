import { useState } from "react";
import { resetPassword } from "../../api.js";
import { Button, ErrorBox } from "../../ui.jsx";

export default function ResetPassword({ initialToken = "", onNavigate }) {
  const [token, setToken] = useState(initialToken);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!token.trim()) {
      setError(new Error("Please enter your password reset token."));
      return;
    }
    if (!newPassword) {
      setError(new Error("Please enter a new password."));
      return;
    }
    if (newPassword.length < 8) {
      setError(new Error("Password must be at least 8 characters long."));
      return;
    }
    if (newPassword !== confirmPassword) {
      setError(new Error("Passwords do not match."));
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await resetPassword({
        token: token.trim(),
        new_password: newPassword,
      });
      setSuccess(true);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-slate-900 p-8 shadow-2xl ring-1 ring-slate-800">
        <div className="text-center">
          <div className="inline-block text-2xl font-bold tracking-tight text-slate-100">
            AgentReliability <span className="text-indigo-400">AI</span>
          </div>
          <h2 className="mt-4 text-xl font-semibold text-slate-200">Set new password</h2>
          <p className="mt-1 text-sm text-slate-400">
            Enter the reset token received and your new password
          </p>
        </div>

        {error && <ErrorBox error={error} />}

        {success ? (
          <div className="space-y-4">
            <div className="rounded-xl bg-emerald-500/10 p-4 text-sm text-emerald-300 ring-1 ring-emerald-500/30">
              <p className="font-semibold">Password updated successfully!</p>
              <p className="mt-1 text-xs text-emerald-400">
                You can now sign in using your new credentials.
              </p>
            </div>
            <Button
              onClick={() => onNavigate("login")}
              className="w-full justify-center py-2.5 text-center text-sm font-semibold"
            >
              Sign In to Your Account
            </Button>
          </div>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="block text-xs font-medium text-slate-300">Reset Token</label>
              <input
                type="text"
                required
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Paste reset token"
                className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-mono text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300">New Password</label>
              <input
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="At least 8 characters"
                className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300">Confirm Password</label>
              <input
                type="password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter new password"
                className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full justify-center py-2.5 text-center text-sm font-semibold"
            >
              {loading ? "Updating password…" : "Update Password"}
            </Button>
          </form>
        )}

        <div className="mt-6 border-t border-slate-800 pt-4 text-center text-xs text-slate-400">
          <button
            onClick={() => onNavigate("login")}
            className="font-medium text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            ← Back to sign in
          </button>
        </div>
      </div>
    </div>
  );
}

