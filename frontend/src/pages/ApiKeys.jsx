import { useState, useEffect, useCallback } from "react";
import { listProjectKeys, createProjectKey, revokeProjectKey, rotateProjectKey, isDemoMode } from "../api.js";
import { Button, Card, Empty, ErrorBox, PageTitle, Badge } from "../ui.jsx";

export default function ApiKeys({ currentProject }) {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState(null); // { key: "ar_...", name: "..." }
  const [copied, setCopied] = useState(false);

  // Rotation / Revocation confirmation state
  const [confirmRotateKey, setConfirmRotateKey] = useState(null);
  const [confirmRevokeKey, setConfirmRevokeKey] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);

  const loadKeys = useCallback(async () => {
    if (!currentProject?.id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listProjectKeys(currentProject.id);
      setKeys(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [currentProject?.id]);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  async function handleCreate(e) {
    e.preventDefault();
    setActionBusy(true);
    setError(null);
    try {
      const res = await createProjectKey(currentProject.id, { name: newKeyName.trim() || "API Key" });
      setNewKeyName("");
      setShowCreateModal(false);
      setCreatedKey({ key: res.api_key, name: res.name });
      await loadKeys();
    } catch (err) {
      setError(err);
    } finally {
      setActionBusy(false);
    }
  }

  async function handleRotate(key) {
    setActionBusy(true);
    setError(null);
    try {
      const res = await rotateProjectKey(currentProject.id, key.id);
      setConfirmRotateKey(null);
      setCreatedKey({ key: res.api_key, name: res.name });
      await loadKeys();
    } catch (err) {
      setError(err);
    } finally {
      setActionBusy(false);
    }
  }

  async function handleRevoke(key) {
    setActionBusy(true);
    setError(null);
    try {
      await revokeProjectKey(currentProject.id, key.id);
      setConfirmRevokeKey(null);
      await loadKeys();
    } catch (err) {
      setError(err);
    } finally {
      setActionBusy(false);
    }
  }

  function copyToClipboard(text) {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  return (
    <div>
      <PageTitle
        title="Project API Keys"
        subtitle={`Manage authentication keys for ${currentProject?.name || "your project"}.`}
      >
        <Button
          onClick={() => setShowCreateModal(true)}
          disabled={isDemoMode()}
          title={isDemoMode() ? "Disabled in Public Demo mode" : undefined}
        >
          {isDemoMode() ? "Key Generation (Demo Protected)" : "+ Generate New API Key"}
        </Button>
      </PageTitle>

      {isDemoMode() && (
        <div className="mb-6 rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4 text-xs text-indigo-200 space-y-1">
          <div className="flex items-center gap-2 font-bold text-indigo-300">
            <svg className="h-4 w-4 shrink-0 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <span>Public Demo Mode — Read-Only Key Protection</span>
          </div>
          <p className="text-[11px] text-slate-300 leading-relaxed">
            Live API key generation and token revelation are disabled in this public demonstration environment. The keys listed below are synthetic demonstration fixtures and cannot be used to authenticate external API calls.
          </p>
        </div>
      )}

      {error && <div className="mb-6"><ErrorBox error={error} /></div>}

      {/* Key Display Modal (Shown EXACTLY once on creation or rotation) */}
      {createdKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl bg-slate-900 p-6 shadow-2xl ring-1 ring-emerald-500/50">
            <div className="flex items-center gap-2 text-emerald-400">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h3 className="text-lg font-bold text-slate-100">Save Your New API Key</h3>
            </div>
            <p className="mt-2 text-xs text-slate-300">
              Please copy this secret key now. For your security, <span className="font-semibold text-emerald-300">it will never be displayed again</span>.
            </p>

            <div className="mt-4 rounded-xl bg-slate-950 p-3 ring-1 ring-slate-800">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {createdKey.name}
              </div>
              <div className="mt-1 flex items-center justify-between gap-2">
                <code className="font-mono text-xs text-emerald-300 break-all select-all">
                  {createdKey.key}
                </code>
                <Button
                  variant="ghost"
                  onClick={() => copyToClipboard(createdKey.key)}
                  className="flex-shrink-0 text-xs py-1"
                >
                  {copied ? "✓ Copied!" : "Copy"}
                </Button>
              </div>
            </div>

            <div className="mt-5 flex justify-end">
              <Button onClick={() => setCreatedKey(null)}>I Have Stored This Key Safely</Button>
            </div>
          </div>
        </div>
      )}

      {/* Keys Table Card */}
      <Card className="mb-8">
        <h2 className="mb-3 font-semibold text-slate-100">Active & Revoked Keys</h2>
        {loading && keys.length === 0 ? (
          <p className="text-sm text-slate-400">Loading API keys…</p>
        ) : keys.length === 0 ? (
          <Empty>No API keys generated for this project yet.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-400">
                <tr>
                  <th className="py-2.5 pr-4">Name</th>
                  <th className="py-2.5 pr-4">Key Identifier</th>
                  <th className="py-2.5 pr-4">Created</th>
                  <th className="py-2.5 pr-4">Last Used</th>
                  <th className="py-2.5 pr-4">Status</th>
                  <th className="py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {keys.map((k) => {
                  const isRevoked = Boolean(k.revoked_at);
                  return (
                    <tr key={k.id} className="hover:bg-slate-800/30 transition">
                      <td className="py-3 pr-4 font-medium text-slate-200">{k.name}</td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                        {k.key_prefix}••••••••••••
                      </td>
                      <td className="py-3 pr-4 text-xs text-slate-400">
                        {new Date(k.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 pr-4 text-xs text-slate-400">
                        {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "Never"}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge tone={isRevoked ? "red" : "green"}>
                          {isRevoked ? "Revoked" : "Active"}
                        </Badge>
                      </td>
                      <td className="py-3 text-right">
                        {!isRevoked && (
                          <div className="flex items-center justify-end gap-2">
                            {isDemoMode() ? (
                              <span className="text-xs text-slate-500 italic">Protected (Demo)</span>
                            ) : (
                              <>
                                <button
                                  onClick={() => setConfirmRotateKey(k)}
                                  className="text-xs text-indigo-400 hover:text-indigo-300 hover:underline"
                                >
                                  Rotate
                                </button>
                                <span className="text-slate-600">|</span>
                                <button
                                  onClick={() => setConfirmRevokeKey(k)}
                                  className="text-xs text-red-400 hover:text-red-300 hover:underline"
                                >
                                  Revoke
                                </button>
                              </>
                            )}
                          </div>
                        )}
                        {isRevoked && (
                          <span className="text-xs text-slate-500">Revoked on {new Date(k.revoked_at).toLocaleDateString()}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Developer Integration Guide */}
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-bold text-indigo-400">1</span>
            <h3 className="font-semibold text-slate-100">Python SDK Usage</h3>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            An API key authenticates your Python agent to ingest execution traces into <b>{currentProject?.name || "your project"}</b>. Set it as an environment variable before running your agent.
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-xs text-indigo-300">
            {`export AGENTRELIABILITY_API_KEY="<your-api-key>"\nexport AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001"`}
          </pre>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-300">
            {`from agentreliability import AgentMonitor\n\nmonitor = AgentMonitor()\n\n@monitor.trace_agent("my-agent")\ndef run(user_query):\n    ...\n`}
          </pre>
          <div className="mt-3 rounded bg-amber-950/30 p-2.5 text-[11px] text-amber-300 border border-amber-500/30">
            ⚠️ <b>Security Notice:</b> Never commit API keys to Git. Complete keys are hashed with SHA-256 and only displayed once at creation time.
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-bold text-indigo-400">2</span>
            <h3 className="font-semibold text-slate-100">GitHub Actions CI/CD</h3>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            Add your key to your GitHub repository under <b>Settings → Secrets and variables → Actions</b> as <code className="font-mono text-indigo-300">AGENTRELIABILITY_API_KEY</code>.
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-300">
            {`- name: Run Agent Regression Tests\n  env:\n    AGENTRELIABILITY_API_KEY: \${{ secrets.AGENTRELIABILITY_API_KEY }}\n  run: |\n    agentreliability test --project ./agent-tests --upload`}
          </pre>
          <div className="mt-3 rounded bg-slate-950 p-2.5 text-[11px] text-slate-400 border border-slate-800">
            💡 <b>Key Management:</b> If an API key is leaked or compromised, click <b>Rotate</b> to issue a new secret key immediately, or <b>Revoke</b> to permanently disable it.
          </div>
        </Card>
      </div>

      {/* Modal: Create Key */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 p-6 shadow-2xl ring-1 ring-slate-800">
            <h3 className="text-lg font-bold text-slate-100">Generate Project API Key</h3>
            <p className="mt-1 text-xs text-slate-400">
              Provide a label to help identify where this key is being used (e.g. "GitHub Actions", "Local Dev").
            </p>
            <form onSubmit={handleCreate} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300">Key Name</label>
                <input
                  type="text"
                  autoFocus
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="e.g. Production CI Key"
                  className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" type="button" onClick={() => setShowCreateModal(false)}>Cancel</Button>
                <Button type="submit" disabled={actionBusy}>{actionBusy ? "Generating…" : "Generate Key"}</Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Rotate Key Confirmation */}
      {confirmRotateKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 p-6 shadow-2xl ring-1 ring-slate-800">
            <h3 className="text-lg font-bold text-amber-300">Rotate API Key</h3>
            <p className="mt-2 text-xs text-slate-300">
              Rotating <span className="font-semibold text-slate-100">"{confirmRotateKey.name}"</span> will immediately invalidate the existing key and issue a new secret key.
            </p>
            <p className="mt-1 text-xs text-amber-400">
              Any CI workflows or agent services using the old key will stop working until updated.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirmRotateKey(null)}>Cancel</Button>
              <Button onClick={() => handleRotate(confirmRotateKey)} disabled={actionBusy}>
                {actionBusy ? "Rotating…" : "Yes, Rotate Key"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Revoke Key Confirmation */}
      {confirmRevokeKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 p-6 shadow-2xl ring-1 ring-slate-800">
            <h3 className="text-lg font-bold text-red-300">Revoke API Key</h3>
            <p className="mt-2 text-xs text-slate-300">
              Are you sure you want to revoke <span className="font-semibold text-slate-100">"{confirmRevokeKey.name}"</span>?
            </p>
            <p className="mt-1 text-xs text-red-400">
              This action cannot be undone. Ingestion requests using this key will immediately return 401 Unauthorized.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirmRevokeKey(null)}>Cancel</Button>
              <Button variant="danger" onClick={() => handleRevoke(confirmRevokeKey)} disabled={actionBusy}>
                {actionBusy ? "Revoking…" : "Revoke Key"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

