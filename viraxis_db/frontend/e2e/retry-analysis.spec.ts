import { test, expect, Page, Locator } from "@playwright/test";

/**
 * Cobertura e2e do botão "Tentar novamente" (RetryAnalysisButton) na
 * Biblioteca — feature `[ARTHUR] Retry na UI para RawVideo com status=failed`
 * (BACKLOG P1, commit be6a723).
 *
 * Não depende de backend real: todas as chamadas same-origin (`/api/...`)
 * são interceptadas via `page.route`, então o que é exercitado de verdade é
 * o componente React + a página da Biblioteca reagindo aos estados reais de
 * resposta HTTP do proxy `POST /api/raw-videos/[id]/reanalyze` — sucesso,
 * erro de rede, 422 (vídeo não elegível) e 429 (rate limit), como pedido na
 * task.
 *
 * Nota de seletor: o card do grid é um `<div role="button">` (para hospedar
 * o botão de retry sem `<button>` aninhado — ver page.tsx). Isso faz o card
 * inteiro também casar com `getByRole("button", { name: "Tentar novamente" })`
 * via texto de descendente, então os testes usam um locator restrito à tag
 * `<button>` real para mirar só o botão de retry.
 */

const OFFICE_ID = "11111111-1111-1111-1111-111111111111";
const VIDEO_ID = "22222222-2222-2222-2222-222222222222";

const FAILED_VIDEO = {
  id: VIDEO_ID,
  office_id: OFFICE_ID,
  title: "Vídeo de teste",
  original_filename: "teste.mp4",
  status: "failed",
  duration_seconds: 42,
  tags: [],
  description: null,
  r2_url: null,
  ai_analysis: { error: "Falha simulada de teste" },
  error_type: "timeout",
  created_at: new Date().toISOString(),
};

function retryButtonLocator(page: Page): Locator {
  return page.locator('button:has-text("Tentar novamente")');
}

/** Mocka as chamadas comuns a toda carga da Biblioteca: usuário admin (pula
 * o gate de onboarding), lista de escritórios e o vídeo `failed` inicial. */
async function mockBibliotecaBaseline(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("viraxis_token", "fake-token-e2e");
    localStorage.setItem(
      "viraxis_user",
      JSON.stringify({ id: "u1", email: "e2e@viraxis.dev", full_name: "E2E", role: "admin" })
    );
  });

  await page.route("**/api/users/me", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: "u1", email: "e2e@viraxis.dev", full_name: "E2E", role: "admin" }),
    })
  );

  await page.route("**/api/offices", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ id: OFFICE_ID, name: "Escritório E2E" }]),
    })
  );

  await page.route(`**/api/raw-videos?office_id=${OFFICE_ID}`, route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([FAILED_VIDEO]),
    })
  );
}

test.describe("Retry na UI para RawVideo com status=failed", () => {
  test("card mostra o botão Tentar novamente para vídeo failed", async ({ page }) => {
    await mockBibliotecaBaseline(page);
    await page.goto(`/dashboard/biblioteca?office_id=${OFFICE_ID}`);

    await expect(retryButtonLocator(page)).toBeVisible();
    // Badge de status inicial confirma que partimos de fato de status=failed.
    await expect(page.getByText("Erro na análise").first()).toBeVisible();
  });

  test("sucesso: loading -> status atualizado para processing sem novo upload", async ({ page }) => {
    await mockBibliotecaBaseline(page);

    let reanalyzeCalled = false;
    let sawAuthHeader = "";
    await page.route(`**/api/raw-videos/${VIDEO_ID}/reanalyze`, async route => {
      reanalyzeCalled = true;
      sawAuthHeader = route.request().headers()["authorization"] ?? "";
      // Atraso proposital para dar tempo de observar o estado de loading real
      // (spinner + botão desabilitado), não só o resultado final.
      await new Promise(r => setTimeout(r, 400));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...FAILED_VIDEO, status: "processing", error_type: null }),
      });
    });

    await page.goto(`/dashboard/biblioteca?office_id=${OFFICE_ID}`);

    const retryButton = retryButtonLocator(page);
    await expect(retryButton).toBeVisible();
    await retryButton.click();

    // Estado de loading real: label muda e o botão fica desabilitado com spinner.
    const loadingButton = page.locator('button:has-text("Reenviando...")');
    await expect(loadingButton).toBeVisible();
    await expect(loadingButton).toBeDisabled();

    // Após a resposta: card reflete status=processing imediatamente (sem
    // esperar o próximo ciclo do polling de 5s) e o botão de retry some,
    // já que status deixou de ser "failed".
    await expect(page.getByText("Analisando...").first()).toBeVisible();
    await expect(retryButtonLocator(page)).toHaveCount(0);

    expect(reanalyzeCalled).toBe(true);
    expect(sawAuthHeader).toBe("Bearer fake-token-e2e");
  });

  test("erro de rede: mensagem inline e botão permanece clicável", async ({ page }) => {
    await mockBibliotecaBaseline(page);

    await page.route(`**/api/raw-videos/${VIDEO_ID}/reanalyze`, route => route.abort("failed"));

    await page.goto(`/dashboard/biblioteca?office_id=${OFFICE_ID}`);
    const retryButton = retryButtonLocator(page);
    await retryButton.click();

    await expect(page.getByText("Erro de rede — verifique sua conexão e tente novamente.")).toBeVisible();
    // Continua elegível para nova tentativa — não fica travado em loading.
    await expect(retryButton).toBeEnabled();
  });

  test("422 (vídeo não está mais failed): mensagem específica, sem crash da página", async ({ page }) => {
    await mockBibliotecaBaseline(page);

    await page.route(`**/api/raw-videos/${VIDEO_ID}/reanalyze`, route =>
      route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Só é possível reanalisar vídeos com status=failed (status atual: processing).",
        }),
      })
    );

    await page.goto(`/dashboard/biblioteca?office_id=${OFFICE_ID}`);
    const retryButton = retryButtonLocator(page);
    await retryButton.click();

    await expect(
      page.getByText("Só é possível reanalisar vídeos com status=failed (status atual: processing).")
    ).toBeVisible();
    await expect(retryButton).toBeEnabled();
  });

  test("429 (rate limit): entra em cooldown com contagem regressiva via Retry-After", async ({ page }) => {
    await mockBibliotecaBaseline(page);

    await page.route(`**/api/raw-videos/${VIDEO_ID}/reanalyze`, route =>
      route.fulfill({
        status: 429,
        contentType: "application/json",
        headers: { "Retry-After": "30" },
        body: JSON.stringify({
          type: "RateLimitExceeded",
          detail: "Muitas tentativas — aguarde antes de tentar novamente.",
          retry_after_seconds: 30,
        }),
      })
    );

    await page.goto(`/dashboard/biblioteca?office_id=${OFFICE_ID}`);
    const retryButton = retryButtonLocator(page);
    await retryButton.click();

    const cooldownButton = page.locator('button:has-text("Aguarde")');
    await expect(cooldownButton).toBeVisible();
    await expect(cooldownButton).toBeDisabled();
    await expect(page.getByText(/Limite de tentativas atingido/)).toBeVisible();
  });
});
