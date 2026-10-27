/**
 * Helper to determine if the application is running in Public Demo Mode.
 *
 * Security Rules:
 * 1. The production website (agentreliability-ai.vercel.app or production domain)
 *    can NEVER activate demo mode under any circumstances, even if ?demo=true is present.
 * 2. URL parameter ?demo=true is ONLY evaluated on localhost/127.0.0.1 for local dev inspection.
 * 3. The separate public demo deployment (agentreliability-demo.vercel.app) or any host
 *    with VITE_DEMO_MODE=true activates demo mode.
 */

const PROD_HOSTNAMES = new Set([
  "agentreliability-ai.vercel.app",
  "app.agentreliability.com",
]);

export function isDemoMode() {
  if (typeof window !== "undefined") {
    const host = (window.location.hostname || "").toLowerCase();

    // 1. HARD SECURITY BLOCK: The production website can NEVER activate demo mode
    if (PROD_HOSTNAMES.has(host)) {
      return false;
    }

    // 2. Explicit demo hostnames (e.g. agentreliability-demo.vercel.app)
    if (host.includes("agentreliability-demo") || host.startsWith("demo.")) {
      return true;
    }

    // 3. Allow query parameter ?demo=true ONLY on localhost / 127.0.0.1 for local dev testing
    const isLocalhost = host === "localhost" || host === "127.0.0.1";
    if (isLocalhost) {
      try {
        const searchParams = new URLSearchParams(window.location.search);
        const demoParam = searchParams.get("demo");
        if (demoParam === "true" || demoParam === "1") {
          return true;
        }
      } catch {
        // Ignore parsing errors
      }
    }
  }

  // 4. Build-time environment variable explicitly set in the separate demo deployment
  if (typeof import.meta !== "undefined" && import.meta.env?.VITE_DEMO_MODE === "true") {
    return true;
  }

  return false;
}
