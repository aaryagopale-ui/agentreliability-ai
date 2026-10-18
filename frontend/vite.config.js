import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The proxy forwards /api calls to the FastAPI backend, so the browser sees one origin.
// Set API_TARGET to point at a different backend (default: http://127.0.0.1:8000).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": process.env.API_TARGET || "http://127.0.0.1:8000" } },
});
