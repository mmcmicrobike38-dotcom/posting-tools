import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const packageJson = JSON.parse(fs.readFileSync(path.resolve(__dirname, "package.json"), "utf8"));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  root: ".",
  base: "./",
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version ?? "0.0.0")
  },
  server: {
    host: process.env.TAURI_DEV_HOST || "127.0.0.1",
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**", "**/storage/**", "**/release/**", "**/dist-python/**", "**/build-python/**"]
    }
  },
  clearScreen: false,
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: process.env.TAURI_ENV_PLATFORM === "windows" ? "chrome105" : "safari13",
    minify: process.env.TAURI_ENV_DEBUG ? false : "esbuild",
    sourcemap: Boolean(process.env.TAURI_ENV_DEBUG),
    outDir: "dist/renderer",
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, "index.html")
    }
  }
});
