/**
 * Kanban — smoke das melhorias Trello-like (B5 + B6, sessão Example User 26/05)
 *
 * Valida em /tasks/kanban (template servido: templates/app/tasks/kanban.html
 * via override em core/app_factory.py:1346, com classes .ch-column/.ch-task-card):
 *
 *   B5: form "Nova lista" no topo do board (ch-kanban-create__form) cria coluna
 *       via POST /tasks/api/columns. Já existia no template novo — esse spec
 *       só valida fluxo.
 *   B6: dblclick no .ch-task-card__title vira input editável; Enter salva via
 *       PUT /tasks/api/{id}/update; Esc restaura. Single click navega pro
 *       detail (preserva UX existente). Example User: "burocrático" ([01:09:27]).
 *
 * Roda:
 *   CASEHUB_SMOKE_BASE_URL=https://sampletenant.casehub.legal/casehub \
 *   CASEHUB_ALLOW_NON_PROD_SMOKE=1 \
 *   CASEHUB_AUDIT_EMAIL=... CASEHUB_AUDIT_PASSWORD=... \
 *   npx playwright test tests/smoke-test-kanban-inline-2026-05-26.spec.js
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

test("Kanban — Nova lista (B5) + dblclick rename de card (B6)", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 900 });

  const config = buildSmokeConfig();
  const getConsoleEntries = attachConsoleWatch(page);

  await ensureAuthenticated(page, config);
  await page.goto(config.url("/tasks/kanban"), { waitUntil: "domcontentloaded" });

  // Sanity: board carrega com ao menos 1 coluna default (Pendente/Em Andamento/...).
  await expect(page.locator(".ch-column").first()).toBeVisible({ timeout: 10_000 });
  await screenshot(page, config, "kanban-loaded");

  // ───── B5: form Nova lista ───────────────────────────────────────────────
  // 1) Form e input visíveis.
  const newListInput = page.locator('#chColumnForm input[name="name"]');
  await expect(newListInput).toBeVisible();
  const newListSubmit = page.locator('#chColumnForm button[type="submit"]');
  await expect(newListSubmit).toBeVisible();

  // 2) Cria lista privada (não exige can_manage_shared_kanban).
  const colName = `Smoke-${Date.now().toString(36).slice(-6)}`;
  await newListInput.fill(colName);
  await page.locator('#chColumnForm select[name="visibility"]').selectOption("private");

  // 3) Submit + redirect → ?view=private; nova coluna aparece.
  await Promise.all([
    page.waitForLoadState("domcontentloaded"),
    newListSubmit.click(),
  ]);
  const createdColumn = page.locator(`.ch-column__name:has-text("${colName}")`);
  await expect(createdColumn).toBeVisible({ timeout: 5_000 });
  await screenshot(page, config, "kanban-b5-column-created");

  // Cleanup (FR-4 pré-Example User 30/05): smoke não pode poluir prod DB com Smoke-XXXX
  // columns visíveis no kanban do escritório. Captura column_id do data attr e
  // dispara DELETE /tasks/api/columns/{id} via fetch autenticado (cookies do
  // page context). Falha silenciosa NÃO quebra o test — flag para inspeção.
  const colSection = page.locator(`.ch-column:has(.ch-column__name:has-text("${colName}"))`);
  const colId = await colSection.getAttribute("data-column-id");
  if (colId) {
    const delResp = await page.evaluate(async (id) => {
      const r = await fetch(`/casehub/tasks/api/columns/${id}`, {
        method: "DELETE",
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      return { status: r.status, ok: r.ok };
    }, colId);
    if (!delResp.ok) {
      console.warn(`[smoke-cleanup] DELETE col ${colId} returned ${delResp.status} — coluna ${colName} pode ter ficado em prod DB`);
    }
  }

  // ───── B6: dblclick no título do card ───────────────────────────────────
  // Volta pra view=all pra ver cards existentes (Pendente etc).
  await page.goto(config.url("/tasks/kanban?view=all"), { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ch-column").first()).toBeVisible();

  // Garantir pelo menos 1 card. Se não houver, criar via quick-add na 1ª coluna.
  let cardTitle = page.locator(".ch-task-card__title").first();
  if ((await cardTitle.count()) === 0) {
    const quick = page.locator('.ch-column__quickadd input[name="title"]').first();
    await quick.fill(`Smoke task ${Date.now().toString(36).slice(-6)}`);
    await Promise.all([
      page.waitForLoadState("domcontentloaded"),
      quick.press("Enter"),
    ]);
    cardTitle = page.locator(".ch-task-card__title").first();
  }
  await expect(cardTitle).toBeVisible();

  const originalText = (await cardTitle.textContent())?.trim() || "";
  expect(originalText.length, "card title must be non-empty").toBeGreaterThan(0);

  // 1) Dblclick troca por input editável.
  await cardTitle.dblclick();
  const cardInput = cardTitle.locator("input");
  await expect(cardInput).toBeVisible({ timeout: 2_000 });
  await expect(cardInput).toBeFocused();
  await expect(cardInput).toHaveValue(originalText);
  await screenshot(page, config, "kanban-b6-title-editing");

  // 2) Esc restaura (sem chamar API).
  await cardInput.press("Escape");
  await expect(cardTitle.locator("input")).toHaveCount(0);
  await expect(cardTitle).toHaveText(originalText);

  // 3) Dblclick + edita + Enter → PUT /api/{id}/update.
  await cardTitle.dblclick();
  const newTitle = `${originalText} · ✎${Date.now().toString(36).slice(-4)}`;
  const cardInput2 = cardTitle.locator("input");
  await cardInput2.fill(newTitle);

  const [putResp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/tasks/api/") && r.url().includes("/update") && r.request().method() === "PUT",
      { timeout: 5_000 }
    ),
    cardInput2.press("Enter"),
  ]);
  expect(putResp.status(), "PUT /tasks/api/{id}/update should succeed").toBe(200);

  // 4) UI reflete novo título.
  await expect(cardTitle.locator("input")).toHaveCount(0);
  await expect(cardTitle).toHaveText(newTitle);
  await screenshot(page, config, "kanban-b6-title-saved");

  // Console clean (best effort).
  const entries = getConsoleEntries();
  const noisyAllow = /favicon|404|preload|preconnect|font|image\/svg|sourcemap/i;
  const real = entries.filter((e) => !noisyAllow.test(e));
  expect(real, `Console errors/warnings:\n${real.join("\n")}`).toEqual([]);
});
