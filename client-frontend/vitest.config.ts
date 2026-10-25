import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { resolve } from "node:path";

/**
 * Rede de regressão do FinTrack no navegador (SPEC-11 §5).
 *
 * Mesma função dos testes do client-backend: é o que o Executor não pode
 * quebrar. Roda em jsdom porque o que interessa é comportamento - o que a
 * pessoa vê e consegue fazer -, não pixels.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(__dirname, ".") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.tsx", "tests/**/*.test.ts"],
  },
});
