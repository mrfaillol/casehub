const crypto = require("crypto");
const { test, expect } = require("@playwright/test");
const {
  applyOptionalStorageState,
  attachConsoleWatch,
  buildSmokeConfig,
  ensureAuthenticated,
  expectConsoleClean,
  screenshot,
} = require("./smoke-legalops-helpers");

applyOptionalStorageState(test);

const viewports = [
  { name: "desktop", size: { width: 1440, height: 900 } },
  { name: "mobile", size: { width: 390, height: 844 } },
];

function signPayload(payload, key) {
  return crypto.createHmac("sha256", key).update(payload).digest("hex");
}

async function findAcceptedKanbanColumn(page, excludeColumnId = null) {
  const accepted = new Set([
    "pending",
    "in_progress",
    "blocked",
    "completed",
    "todo",
    "to_do",
    "a_fazer",
    "pendente",
    "doing",
    "em_andamento",
    "done",
    "concluida",
    "concluido",
  ]);
  const columns = page.locator(".kanban-column");
  const count = await columns.count();

  for (let index = 0; index < count; index += 1) {
    const column = columns.nth(index);
    const status = await column.getAttribute("data-status");
    const columnId = await column.getAttribute("data-col-id");
    if (status && columnId && accepted.has(status) && columnId !== excludeColumnId) {
      return { column, status, columnId };
    }
  }

  throw new Error("Expected at least one Kanban column with an accepted task status.");
}

for (const viewport of viewports) {
  test(`LegalOps #344 authenticated Kanban user flow with receiver default-off (${viewport.name})`, async ({ page }) => {
    test.setTimeout(90000);
    await page.setViewportSize(viewport.size);

    const config = buildSmokeConfig();
    const getConsoleEntries = attachConsoleWatch(page);
    const stamp = `${Date.now()}-${viewport.name}`;
    const title = `QA Kanban ${stamp}`;

    await ensureAuthenticated(page, config);
    await page.goto(config.url("/tasks/kanban"), { waitUntil: "domcontentloaded" });
    await expect(page.locator(".kanban-board")).toBeVisible();
    await screenshot(page, config, `344-${viewport.name}-kanban-initial`);

    const sourceColumn = await findAcceptedKanbanColumn(page);
    const firstInput = sourceColumn.column.locator(".quick-add-input").first();
    await expect(firstInput).toBeVisible();
    await firstInput.fill(title);
    await firstInput.press("Enter");
    await expect(page.locator(".kanban-card", { hasText: title })).toBeVisible({ timeout: 15000 });

    const card = page.locator(".kanban-card", { hasText: title }).first();
    const taskId = await card.getAttribute("data-task-id");
    expect(taskId).toBeTruthy();

    const targetColumn = await findAcceptedKanbanColumn(page, sourceColumn.columnId);

    const moveResponse = await page.request.patch(config.url(`/tasks/api/${taskId}/move`), {
      data: { status: targetColumn.status, position: 0, column_id: targetColumn.columnId },
    });
    expect(moveResponse.ok(), await moveResponse.text()).toBe(true);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(
      page.locator(`.kanban-column[data-col-id="${targetColumn.columnId}"] .kanban-card[data-task-id="${taskId}"]`, {
        hasText: title,
      })
    ).toBeVisible({ timeout: 15000 });
    await screenshot(page, config, `344-${viewport.name}-kanban-moved`);

    if (process.env.CASEHUB_SMOKE_RECEIVER_ENABLED === "1") {
      test.info().annotations.push({ type: "receiver", description: "default-off assertion skipped on enabled target" });
    } else {
      const receiverResponse = await page.request.post(config.url("/api/v1/improvement-tasks"), {
        data: {
          envelope_ref: `smoke-disabled-${stamp}`,
          kind: "ui-polish",
          title: "Receiver disabled smoke",
        },
      });
      expect(receiverResponse.status()).toBe(503);
    }
    await expectConsoleClean(getConsoleEntries);
  });
}

test("LegalOps #344 receiver HMAC accepts only valid signed payload when explicitly enabled", async ({ request }) => {
  const key = process.env.CASEHUB_SMOKE_IMPROVEMENT_HMAC_KEY;
  test.skip(
    process.env.CASEHUB_SMOKE_RECEIVER_ENABLED !== "1" || !key,
    "Set CASEHUB_SMOKE_RECEIVER_ENABLED=1 and CASEHUB_SMOKE_IMPROVEMENT_HMAC_KEY for an enabled receiver target."
  );

  const config = buildSmokeConfig();
  const stamp = Date.now();
  const payload = JSON.stringify({
    envelope_ref: `smoke-hmac-${stamp}`,
    kind: "ui-polish",
    title: "Receiver HMAC smoke",
    summary: "Valid signed receiver smoke from Playwright",
  });

  const bad = await request.post(config.url("/api/v1/improvement-tasks"), {
    data: payload,
    headers: {
      "content-type": "application/json",
      "x-cmd-ingest-signature": "0".repeat(64),
    },
  });
  expect(bad.status()).toBe(401);

  const good = await request.post(config.url("/api/v1/improvement-tasks"), {
    data: payload,
    headers: {
      "content-type": "application/json",
      "x-cmd-ingest-signature": signPayload(payload, key),
    },
  });
  expect([200, 201]).toContain(good.status());
  const json = await good.json();
  expect(json.ok).toBe(true);
  expect(json.envelope_ref || `smoke-hmac-${stamp}`).toBe(`smoke-hmac-${stamp}`);
});
