/**
 * Isolated browser session storage for Public Demo Sandbox.
 *
 * Ensures each visitor's browser tab has an independent, persistent sandbox session:
 * - Mutations (projects created, tests executed, baselines updated, logs uploaded)
 *   are isolated strictly to the visitor's browser session.
 * - Refreshing the page preserves the visitor's in-progress demo state.
 * - Opening the website in a new window/tab or private tab starts a fresh, clean sandbox.
 * - Clicking "Reset Demo" clears the session storage and restores the pristine demo datasets.
 * - If sessionStorage is unavailable (e.g. Node tests or restricted iframe), seamlessly falls
 *   back to an in-memory dictionary.
 */

const STORAGE_KEY = "ar_demo_sandbox_v2";

class DemoStorage {
  constructor() {
    this.memoryState = null;
  }

  isSessionStorageAvailable() {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return false;
      const testKey = "__ar_test__";
      window.sessionStorage.setItem(testKey, "1");
      window.sessionStorage.removeItem(testKey);
      return true;
    } catch {
      return false;
    }
  }

  load(initialFactory) {
    if (this.isSessionStorageAvailable()) {
      try {
        const raw = window.sessionStorage.getItem(STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && parsed.projects && parsed.projects.length > 0) {
            return parsed;
          }
        }
      } catch (err) {
        console.warn("Could not load demo state from sessionStorage:", err);
      }
    }

    if (this.memoryState) {
      return JSON.parse(JSON.stringify(this.memoryState));
    }

    const fresh = initialFactory();
    this.save(fresh);
    return fresh;
  }

  save(state) {
    this.memoryState = JSON.parse(JSON.stringify(state));
    if (this.isSessionStorageAvailable()) {
      try {
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      } catch (err) {
        console.warn("Could not persist demo state to sessionStorage:", err);
      }
    }
  }

  clear() {
    this.memoryState = null;
    if (this.isSessionStorageAvailable()) {
      try {
        window.sessionStorage.removeItem(STORAGE_KEY);
      } catch (err) {
        console.warn("Could not clear demo state from sessionStorage:", err);
      }
    }
  }
}

export const demoStorage = new DemoStorage();

