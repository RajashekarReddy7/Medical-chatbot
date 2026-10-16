import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Only forward API calls (POST) to the backend; GET /login is a client-side route.
const toBackend = {
  target: "http://localhost:8000",
  bypass: (req) => (req.method === "GET" ? req.url : undefined),
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/login": toBackend,
      "/register": toBackend,
    },
  },
});
