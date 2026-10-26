import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The proxy forwards /api calls to the FastAPI backend, so the browser sees one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0", // Binds both IPv4 (127.0.0.1) and IPv6 (::1/localhost) for Safari & Chrome
    port: 5174,
    proxy: {
      "/api": {
        target: process.env.API_TARGET || "http://127.0.0.1:8001",
        changeOrigin: true,
        secure: false,
        configure: (proxy) => {
          proxy.on("error", (_err, _req, res) => {
            if (res && !res.headersSent) {
              res.writeHead(502, { "Content-Type": "application/json" });
              res.end(
                JSON.stringify({
                  detail: `Backend proxy error: Unable to reach backend at ${
                    process.env.API_TARGET || "http://127.0.0.1:8001"
                  }. Ensure 'agentreliability dev' is running.`,
                })
              );
            }
          });
        },
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 5174,
  },
});
