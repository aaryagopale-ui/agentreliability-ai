import { useState, useRef, useEffect } from "react";
import { createProject, updateProject, archiveProject } from "../api.js";
import { Button, ErrorBox } from "../ui.jsx";

export default function ProjectSwitcher({
  projects,
  currentProject,
  onSelectProject,
  onProjectsUpdated,
  onKeyGenerated,
}) {
  const [open, setOpen] = useState(false);
  const [modalMode, setModalMode] = useState(null); // 'create' | 'rename' | 'archive' | null
  const [projectName, setProjectName] = useState("");
  const [confirmName, setConfirmName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const menuRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function openModal(mode) {
    setError(null);
    setModalMode(mode);
    setOpen(false);
    if (mode === "rename") {
      setProjectName(currentProject?.name || "");
    } else {
      setProjectName("");
      setConfirmName("");
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (!projectName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await createProject({ name: projectName.trim() });
      await onProjectsUpdated();
      onSelectProject({ id: res.id, name: res.name });
      setModalMode(null);
      if (res.api_key && onKeyGenerated) {
        onKeyGenerated({ key: res.api_key, projectName: res.name });
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleRename(e) {
    e.preventDefault();
    if (!projectName.trim() || !currentProject) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await updateProject(currentProject.id, { name: projectName.trim() });
      await onProjectsUpdated();
      onSelectProject(updated);
      setModalMode(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleArchive(e) {
    e.preventDefault();
    if (!currentProject) return;
    if (confirmName.trim() !== currentProject.name) {
      setError(new Error(`Please type "${currentProject.name}" exactly to confirm archival.`));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await archiveProject(currentProject.id, { confirm_name: confirmName.trim() });
      const updatedList = await onProjectsUpdated();
      // Select the first remaining project or null
      if (updatedList && updatedList.length > 0) {
        onSelectProject(updatedList[0]);
      }
      setModalMode(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative" ref={menuRef}>
      {/* Project selector button in header/sidebar */}
      <div className="px-3 py-2">
        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Project</label>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="mt-1 flex w-full items-center justify-between rounded-lg bg-slate-800/80 px-3 py-2 text-left text-sm font-semibold text-slate-100 hover:bg-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition border border-slate-700/60"
        >
          <div className="flex items-center gap-2 truncate">
            <span className={`h-2 w-2 rounded-full ${currentProject ? "bg-emerald-400" : "bg-amber-400"}`}></span>
            <span className="truncate">{currentProject?.name || (projects.length === 0 ? "No Projects (Create One)" : "Select Project")}</span>
          </div>
          <svg className={`h-4 w-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Dropdown Menu */}
      {open && (
        <div className="absolute left-2 right-2 z-50 mt-1 rounded-xl bg-slate-900 py-1.5 shadow-2xl ring-1 ring-slate-700/70">
          <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Your Projects ({projects.length})
          </div>

          {projects.length === 0 ? (
            <div className="px-3 py-3 text-xs text-slate-400 text-center">
              No projects created yet in this database.
            </div>
          ) : (
            <div className="max-h-52 overflow-y-auto">
              {projects.map((p) => {
                const isSelected = p.id === currentProject?.id;
                return (
                  <button
                    key={p.id}
                    onClick={() => {
                      onSelectProject(p);
                      setOpen(false);
                    }}
                    className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition ${
                      isSelected ? "bg-indigo-600/20 text-indigo-300 font-medium" : "text-slate-300 hover:bg-slate-800 hover:text-slate-100"
                    }`}
                  >
                    <span className="truncate">{p.name}</span>
                    {isSelected && (
                      <svg className="h-4 w-4 text-indigo-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          <div className="my-1 border-t border-slate-800"></div>

          <button
            onClick={() => openModal("create")}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-indigo-400 hover:bg-slate-800 hover:text-indigo-300"
          >
            <span>+ Create New Project</span>
          </button>

          {currentProject && (
            <>
              <button
                onClick={() => openModal("rename")}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              >
                <span>✎ Rename Project</span>
              </button>
              {projects.length > 1 && (
                <button
                  onClick={() => openModal("archive")}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-red-400 hover:bg-slate-800 hover:text-red-300"
                >
                  <span>🗑 Archive Project</span>
                </button>
              )}
            </>
          )}
        </div>
      )}

      {/* Modal: Create Project */}
      {modalMode === "create" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 p-6 shadow-2xl ring-1 ring-slate-800">
            <h3 className="text-lg font-bold text-slate-100">Create New Project</h3>
            <p className="mt-1 text-xs text-slate-400">
              Projects isolate agent executions, test cases, traces, and API keys.
            </p>
            {error && <div className="mt-3"><ErrorBox error={error} /></div>}
            <form onSubmit={handleCreate} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300">Project Name</label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Support Agent V2"
                  className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" type="button" onClick={() => setModalMode(null)}>Cancel</Button>
                <Button type="submit" disabled={loading}>{loading ? "Creating…" : "Create Project"}</Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Rename Project */}
      {modalMode === "rename" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 p-6 shadow-2xl ring-1 ring-slate-800">
            <h3 className="text-lg font-bold text-slate-100">Rename Project</h3>
            <p className="mt-1 text-xs text-slate-400">Change the display name of this project.</p>
            {error && <div className="mt-3"><ErrorBox error={error} /></div>}
            <form onSubmit={handleRename} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300">New Project Name</label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" type="button" onClick={() => setModalMode(null)}>Cancel</Button>
                <Button type="submit" disabled={loading}>{loading ? "Saving…" : "Save Changes"}</Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Archive Project with Confirmation */}
      {modalMode === "archive" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 p-6 shadow-2xl ring-1 ring-slate-800">
            <h3 className="text-lg font-bold text-red-300">Archive Project</h3>
            <p className="mt-1 text-xs text-slate-400">
              Archiving hides this project and its test cases, traces, and keys. To prevent accidental archival, please type <span className="font-semibold text-slate-200">"{currentProject?.name}"</span> below.
            </p>
            {error && <div className="mt-3"><ErrorBox error={error} /></div>}
            <form onSubmit={handleArchive} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300">Confirmation</label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={confirmName}
                  onChange={(e) => setConfirmName(e.target.value)}
                  placeholder={currentProject?.name}
                  className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" type="button" onClick={() => setModalMode(null)}>Cancel</Button>
                <Button variant="danger" type="submit" disabled={loading || confirmName.trim() !== currentProject?.name}>
                  {loading ? "Archiving…" : "Archive Project"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

