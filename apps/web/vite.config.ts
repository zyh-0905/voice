import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  test: {
    // Keep unit tests isolated from Playwright specs under tests/e2e.
    include: ["tests/unit/**/*.spec.ts"],
    exclude: ["tests/e2e/**", "node_modules/**"],
    environment: "node",
  },
});
