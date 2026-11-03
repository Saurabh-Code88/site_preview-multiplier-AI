import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API + screenshot requests to FastAPI so no CORS setup is needed in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/screenshots": "http://localhost:8000",
    },
  },
});
