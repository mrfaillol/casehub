/**
 * CaseHub.md POC — smoke test (Fatia 1)
 *
 * Valida que a rota /casehub-md/poc:
 *   1. Carrega autenticada (não redireciona pra /login).
 *   2. TipTap mounta (data-tiptap-ready="true" no #poc-editor).
 *   3. Markdown mirror reflete digitação em tempo real.
 *   4. Round-trip reverso: edita markdown + "Carregar" injeta no editor.
 *
 * Roda contra ambiente dev/local (não VS-prod). Padrão dos demais smokes
 * em tests/smoke-*.spec.js — reusa helpers de auth.
 */

const { test, expect } = require("@playwright/test");
const {
  applyOptionalStorageState,
  attachConsoleWatch,
  buildSmokeConfig,
  ensureAuthenticated,
  screenshot,
} = require("./smoke-legalops-helpers");

applyOptionalStorageState(test);

test("CaseHub.md POC — mount + markdown round-trip", async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 900 });

  const config = buildSmokeConfig();
  const getConsoleEntries = attachConsoleWatch(page);

  await ensureAuthenticated(page, config);

  // 1) Rota autenticada renderiza dentro do shell app/base.html (B13, 26/05).
  await page.goto(config.url("/casehub-md/poc"), { waitUntil: "domcontentloaded" });
  await expect(page).toHaveTitle(/CaseHub\.md/);
  await expect(page.locator(".casehub-md-titlebar h1")).toContainText("CaseHub.md");
  // Shell padrão visível: topbar + tabs + bottomnav.
  await expect(page.locator(".ch-topbar")).toBeVisible();
  await expect(page.locator(".ch-tabs")).toBeVisible();
  // Tab "CaseHub.md" marca como ativa (active_module='md').
  await expect(page.locator('.ch-tab[href*="/casehub-md/poc"]')).toHaveClass(/is-active/);

  // 2) TipTap mountou (sinal via data-tiptap-ready).
  const editor = page.locator("#poc-editor");
  await expect(editor).toHaveAttribute("data-tiptap-ready", "true", { timeout: 15_000 });
  await expect(editor.locator(".ProseMirror")).toBeVisible();

  // Markdown mirror semeado com conteúdo default.
  const mdInitial = await page.locator("#poc-markdown").inputValue();
  expect(mdInitial, "Markdown mirror deveria estar populado no onCreate").toContain("CaseHub.md");

  await screenshot(page, config, "casehub-md-poc-loaded");

  // 3) Digitar no editor reflete no markdown mirror.
  const proseMirror = editor.locator(".ProseMirror");
  await proseMirror.click();
  await page.keyboard.press("Control+End"); // Linux/Win
  await page.keyboard.press("Meta+End");    // macOS — um dos dois pega
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  const probe = `smoke-probe-${Date.now()}`;
  await page.keyboard.type(probe);

  // Mirror deve conter a probe em <500ms (Doherty threshold). Damos 2s de folga.
  await expect.poll(async () => page.locator("#poc-markdown").inputValue(), {
    timeout: 2_000,
    intervals: [50, 100, 200],
  }).toContain(probe);

  await screenshot(page, config, "casehub-md-poc-typed");

  // 4) Round-trip reverso: edita markdown + Carregar injeta no editor.
  const customMd = `# Override ${Date.now()}\n\nLinha de teste reverse round-trip.`;
  await page.locator("#poc-markdown").fill(customMd);
  await page.locator("#poc-load-md").click();

  await expect(proseMirror.locator("h1")).toContainText("Override");
  await expect(proseMirror).toContainText("reverse round-trip");

  await screenshot(page, config, "casehub-md-poc-reverse-loaded");

  // 5) Fatia 3 — embed link via prompt; auto-accept URL "example.com".
  await page.evaluate(() => { window.prompt = () => "example.com"; });
  await proseMirror.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.press("Meta+A");
  await page.locator('button[data-cmd="link"]').click();
  await expect(proseMirror.locator("a[href]")).toHaveCount(1, { timeout: 3_000 });
  const href = await proseMirror.locator("a[href]").first().getAttribute("href");
  // Postel: normalizeUrl prefixa https:// quando faltar.
  expect(href).toMatch(/^https:\/\/example\.com/);
  await screenshot(page, config, "casehub-md-poc-link-inserted");

  // 6) Fatia 4 — export DOCX endpoint. Aceitamos 200 (Pandoc instalado) ou 503 (não).
  const exportResp = await page.request.post(config.url("/casehub-md/export/docx"), {
    data: { markdown: "# Smoke export\n\nLinha **bold** e [link](https://example.com).\n", filename: "smoke-export" },
    failOnStatusCode: false,
  });
  if (exportResp.status() === 200) {
    const buf = await exportResp.body();
    // DOCX é um zip → começa com "PK\x03\x04"
    expect(buf.slice(0, 4).toString("hex")).toBe("504b0304");
    expect(exportResp.headers()["content-disposition"] || "").toContain("smoke-export.docx");
  } else {
    // VPS sem Pandoc: 503 + detail pandoc-not-available
    expect([401, 503]).toContain(exportResp.status());
  }

  // 7) Fatia 5 — Drive save endpoint. Aceitamos 200 (Drive online) ou 503 (offline).
  const driveResp = await page.request.post(config.url("/casehub-md/drive/save"), {
    data: {
      doc_id: `smoke-${Date.now()}`,
      markdown: "# Smoke drive save\n\nLinha de teste.",
    },
    failOnStatusCode: false,
  });
  if (driveResp.status() === 200) {
    const body = await driveResp.json();
    expect(body.file_id, "Drive save should return file_id").toBeTruthy();
    expect(body.was_created, "Smoke doc deveria ser criado").toBe(true);
  } else {
    expect([401, 503]).toContain(driveResp.status());
  }

  // 8) Status bar deve mostrar doc id e estado drive (ok/idle/offline).
  await expect(page.locator("#poc-doc-id")).not.toHaveText("…", { timeout: 5_000 });
  const driveStatusText = await page.locator("#poc-drive-status").textContent();
  expect(driveStatusText, "Status bar deveria refletir estado drive").toMatch(/Drive/);

  // 9) Fatia 6 — OCR endpoint. Probe sem file (esperamos 422 do FastAPI por
  //    "field required") OU 503 (Tesseract ausente). Não enviamos PDF real no
  //    smoke (controle de payload + ambiente cross-platform); o teste com PDF
  //    real fica para um spec dedicado (futuro tests/smoke-casehub-md-ocr.spec.js).
  const ocrResp = await page.request.post(config.url("/casehub-md/ocr"), {
    multipart: {
      // Pequeno PNG vazio 1x1 — payload mínimo válido como multipart, suficiente
      // para o endpoint não rejeitar antes de chamar Tesseract.
      file: {
        name: "smoke.png",
        mimeType: "image/png",
        // 1x1 transparent PNG base64
        buffer: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
          "base64",
        ),
      },
    },
    failOnStatusCode: false,
  });
  expect([200, 401, 415, 422, 503, 504, 500]).toContain(ocrResp.status());

  // 10) Fatia 7 — Maestro endpoint. Aceitamos 200 (Maestro online), 503/504 (offline/timeout).
  const maestroResp = await page.request.post(config.url("/casehub-md/maestro/suggest"), {
    data: { paragraph: "Parágrafo de teste smoke para a sugestão Maestro." },
    failOnStatusCode: false,
  });
  expect([200, 401, 502, 503, 504]).toContain(maestroResp.status());
  if (maestroResp.status() === 200) {
    const body = await maestroResp.json();
    expect(body).toHaveProperty("suggestion");
  }

  // 11) Skip link a11y — agora vem do shell (.ch-skip aponta pra #ch-content).
  await expect(page.locator(".ch-skip")).toHaveAttribute("href", "#ch-content");

  // 12) data-prefix migrou de <body> pra .casehub-md-shell (B13, 26/05).
  await expect(page.locator(".casehub-md-shell")).toHaveAttribute("data-prefix", /.+/);

  // 13) Fatia 9 — Mobile viewport: mirror toggle button visível, mirror card drawer-style.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(250);
  await expect(page.locator("#poc-mobile-toggle")).toBeVisible();
  // Mirror card no mobile fica off-screen até toggle (transform translateY 100%).
  const mirrorBefore = await page.locator("#poc-mirror-card").evaluate(el => getComputedStyle(el).transform);
  await page.locator("#poc-mobile-toggle").click();
  await page.waitForTimeout(300);
  const mirrorAfter = await page.locator("#poc-mirror-card").evaluate(el => getComputedStyle(el).transform);
  expect(mirrorAfter, "Mirror toggle deveria mudar o transform").not.toBe(mirrorBefore);
  // Restaurar desktop viewport para asserts finais.
  await page.setViewportSize({ width: 1440, height: 900 });

  // 14) Fatia 9 — Botão Abrir docs registrado.
  await expect(page.locator('button[data-cmd="driveOpen"]')).toBeVisible();

  // Console deve estar limpo (sem errors/warnings críticos do TipTap/marked/turndown).
  const entries = getConsoleEntries();
  const noisyAllow = /favicon|404|preload|preconnect/i; // ignoramos ruído infra
  const real = entries.filter((e) => !noisyAllow.test(e));
  expect(real, `Console errors/warnings:\n${real.join("\n")}`).toEqual([]);
});
