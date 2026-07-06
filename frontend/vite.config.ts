import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      // Forward API + SSE requests to the FastAPI backend.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // Dev-only endpoints (token minting, bootstrap, JWKS) + health check.
      "/dev": { target: "http://localhost:8000", changeOrigin: true },
      "/oidc": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
