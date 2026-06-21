import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API calls to the FastAPI backend during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/plan": "https://travel-agent-1-zm2s.onrender.com",
      "/health": "https://travel-agent-1-zm2s.onrender.com",
    },
  },
});
