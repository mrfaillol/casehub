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

function idFromPath(url, segment) {
  const parts = new URL(url).pathname.split("/");
  const index = parts.indexOf(segment);
  if (index === -1 || !parts[index + 1]) {
    throw new Error(`Could not extract ${segment} id from ${url}`);
  }
  return parts[index + 1];
}

async function submitAndWaitForPath(page, pathPattern, clickSelector) {
  await Promise.all([
    page.waitForURL(pathPattern, { timeout: 15000 }),
    page.locator(clickSelector).first().click(),
  ]);
}

async function expectRedirect(response, label) {
  expect([200, 302, 303], `${label} status: ${response.status()} ${await response.text()}`).toContain(
    response.status()
  );
}

async function selectFirstNonEmptyOption(page, selector) {
  const optionValue = await page
    .locator(`${selector} option`)
    .evaluateAll((options) => options.find((option) => option.value.trim())?.value || "");
  expect(optionValue, `Expected ${selector} to have at least one non-empty option`).toBeTruthy();
  await page.selectOption(selector, optionValue);
}

for (const viewport of viewports) {
  test(`LegalOps #346 authenticated cadastro/processos smoke (${viewport.name})`, async ({ page }) => {
    test.setTimeout(120000);
    await page.setViewportSize(viewport.size);

    const config = buildSmokeConfig();
    const getConsoleEntries = attachConsoleWatch(page);
    const stamp = `${Date.now()}-${viewport.name}`;
    const firstName = `QA${stamp}`;
    const editedFirstName = `QAEdit${stamp}`;
    const lastName = "LegalOps";
    const email = `qa+${stamp}@example.test`;
    const caseNumber = `CNJ-${stamp}`;
    const editedCaseName = `Caso editado ${stamp}`;
    const processName = `Fluxo QA ${stamp}`;

    await ensureAuthenticated(page, config);

    await page.goto(config.url("/clients/new"), { waitUntil: "domcontentloaded" });
    await expect(page.locator("#clients-form-title")).toBeVisible();
    await page.fill('input[name="first_name"]', firstName);
    await page.fill('input[name="last_name"]', lastName);
    await page.fill('input[name="email"]', email);
    await page.fill('input[name="phone"]', "+55 32 99999-0000");
    await page.selectOption('select[name="status"]', "active");
    await page.fill('textarea[name="notes"]', `LegalOps smoke create ${stamp}`);
    await screenshot(page, config, `346-${viewport.name}-client-new`);
    await submitAndWaitForPath(page, /\/clients\/\d+$/, 'button[type="submit"]');
    const clientId = idFromPath(page.url(), "clients");
    await expect(page.locator("body")).toContainText(firstName);
    await expect(page.locator("body")).toContainText(lastName);
    await screenshot(page, config, `346-${viewport.name}-client-detail`);

    await page.goto(config.url(`/clients/${clientId}/edit`), { waitUntil: "domcontentloaded" });
    await page.fill('input[name="first_name"]', editedFirstName);
    await page.fill('textarea[name="notes"]', `LegalOps smoke edit ${stamp}`);
    await submitAndWaitForPath(page, new RegExp(`/clients/${clientId}$`), 'button[type="submit"]');
    await expect(page.locator("body")).toContainText(editedFirstName);

    await page.goto(config.url(`/clients?search=${encodeURIComponent(email)}`), { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toContainText(editedFirstName);
    await expect(page.locator("body")).toContainText(email);
    await screenshot(page, config, `346-${viewport.name}-client-list`);

    await page.goto(config.url(`/cases/new?client_id=${clientId}`), { waitUntil: "domcontentloaded" });
    await expect(page.locator("#cases-form-title")).toBeVisible();
    await page.selectOption('select[name="client_id"]', clientId);
    await page.fill('input[name="case_number"]', caseNumber);
    await page.fill('input[name="case_name"]', `Caso QA ${stamp}`);
    await page.selectOption('select[name="status"]', "intake");
    await page.selectOption('select[name="priority"]', "high");
    await page.fill('textarea[name="notes"]', `LegalOps case create ${stamp}`);
    await screenshot(page, config, `346-${viewport.name}-case-new`);
    await submitAndWaitForPath(page, /\/cases\/\d+$/, 'button[type="submit"]');
    const caseId = idFromPath(page.url(), "cases");
    await expect(page.locator("body")).toContainText(caseNumber);
    await expect(page.locator("body")).toContainText(editedFirstName);

    await page.goto(config.url(`/cases/${caseId}/edit`), { waitUntil: "domcontentloaded" });
    await page.fill('input[name="case_name"]', editedCaseName);
    await page.selectOption('select[name="priority"]', "urgent");
    await submitAndWaitForPath(page, new RegExp(`/cases/${caseId}$`), 'button[type="submit"]');
    await expect(page.locator("body")).toContainText(editedCaseName);

    await page.goto(config.url(`/cases?search=${encodeURIComponent(caseNumber)}`), { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toContainText(caseNumber);
    await screenshot(page, config, `346-${viewport.name}-case-list`);

    await page.goto(config.url("/processes/new"), { waitUntil: "domcontentloaded" });
    await expect(page.locator("#processes-form-title")).toBeVisible();
    await page.fill('input[name="name"]', processName);
    await page.fill('textarea[name="description"]', `LegalOps process definition ${stamp}`);
    await selectFirstNonEmptyOption(page, 'select[name="area_of_practice"]');
    await page.fill('input[name="estimated_days"]', "21");
    await screenshot(page, config, `346-${viewport.name}-process-new`);
    await submitAndWaitForPath(page, /\/processes$/, 'button[type="submit"]');
    await expect(page.locator("body")).toContainText(processName);

    await page.getByRole("link", { name: processName }).first().click();
    await page.waitForURL(/\/processes\/\d+$/, { timeout: 15000 });
    const processId = idFromPath(page.url(), "processes");
    await expect(page.locator("body")).toContainText(processName);

    const addStepResponse = await page.request.post(config.url(`/processes/${processId}/steps/add`), {
      form: {
        name: `Etapa QA ${stamp}`,
        description: "Etapa criada pelo smoke LegalOps",
        estimated_days: "7",
        is_milestone: "true",
        auto_start_next: "true",
      },
      maxRedirects: 0,
    });
    await expectRedirect(addStepResponse, "process step add");

    const assignResponse = await page.request.post(config.url(`/processes/case/${caseId}/assign`), {
      form: {
        process_id: processId,
        start_date: new Date().toISOString().slice(0, 10),
      },
      maxRedirects: 0,
    });
    await expectRedirect(assignResponse, "case process assignment");

    await page.goto(config.url(`/processes/case/${caseId}/progress`), { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toContainText(editedCaseName);
    await expect(page.locator("body")).toContainText(processName);
    await expect(page.locator("body")).toContainText(`Etapa QA ${stamp}`);
    await screenshot(page, config, `346-${viewport.name}-case-process-progress`);

    await page.goto(config.url(`/clients/${clientId}`), { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toContainText(caseNumber);
    await expect(page.locator("body")).toContainText(editedCaseName);

    await expectConsoleClean(getConsoleEntries);
  });
}
