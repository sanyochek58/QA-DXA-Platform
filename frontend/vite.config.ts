import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// В разработке фронт на :5173, а запросы /api и /health проксируются в core на :8000.
// Так браузер видит один origin и CORS не нужен.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      // графики тяжёлые — отдельным чанком, чтобы экран входа грузился быстро
      output: { manualChunks: { charts: ["recharts"], vendor: ["react", "react-dom", "react-router-dom"] } },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.VITE_API_TARGET ?? "http://localhost:8000", changeOrigin: true },
    },
  },
});
