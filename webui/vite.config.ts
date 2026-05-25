import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
  },
  build: {
    outDir: "../src/harnesslab/web/static_ts",
    emptyOutDir: true,
  },
});
