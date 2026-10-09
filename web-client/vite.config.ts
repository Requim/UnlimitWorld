import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": process.env.M5_API_URL ?? "http://127.0.0.1:8787",
      "/health": process.env.M5_API_URL ?? "http://127.0.0.1:8787",
    },
  },
});
