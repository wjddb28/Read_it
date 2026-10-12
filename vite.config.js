import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
const project = fileURLToPath(new URL(".", import.meta.url));
export default defineConfig({
  root: "templates",
  publicDir: false,
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: [project] },
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: {
    outDir: "../static/react-build",
    emptyOutDir: true,
  },
});
