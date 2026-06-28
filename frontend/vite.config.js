import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy API + media calls to the local backend.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/media": "http://localhost:8000",
    },
  },
});
