import { defineConfig, devices } from "@playwright/test";

// Config mínima e local (sem CI dedicado ainda) para os testes e2e de
// viraxis_db/frontend/e2e/. Sobe o próprio `next dev` e roda contra ele —
// os testes não dependem do backend real (Render/Neon/Supabase): todas as
// chamadas de API são interceptadas via page.route() para exercitar o
// comportamento real do componente/página sem rede externa.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3100",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npx next dev -p 3100",
    url: "http://localhost:3100",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
