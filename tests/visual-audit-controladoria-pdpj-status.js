const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

test('controladoria template exposes PDPJ API status surfaces', async ({ page }) => {
  const templatePath = path.join(process.cwd(), 'templates/controladoria/dashboard.html');
  const template = fs.readFileSync(templatePath, 'utf8');
  const routePath = path.join(process.cwd(), 'routes/controladoria.py');
  const route = fs.readFileSync(routePath, 'utf8');

  expect(template).toContain('id="controladoriaApiSummary"');
  expect(template).toContain('id="intimacoesApiStatus"');
  expect(template).toContain('id="intimacoesApiProvider"');
  expect(template).toContain('id="intimacoesApiProviderStatus"');
  expect(template).toContain('id="intimacoesApiReason"');
  expect(template).toContain('id="intimacoesApiChain"');
  expect(template).toContain('id="intimacoesImportarBtn"');
  expect(template).toContain('importable !== false');
  expect(template).toContain('data-testid="controladoria-api-actions"');
  expect(template).toContain('Buscar subsidiarias');
  expect(template).toContain('{{ api_card.badge_text }}');
  expect(route).toContain('Oficial PDPJ');
  expect(route).toContain('Fallback publico');
  expect(route).toContain('Chave ausente');
  expect(template).toContain('class="ctrl-overdue-mobile-alert"');
  expect(template).toContain('ctrl-mobile-cell-label');
  expect(template).toContain('content: "\\00d7"');
  expect(template).toContain('Confira a lista de prazos vencidos');
  expect(template).toContain("window.matchMedia('(max-width: 700px)')");
  expect(template).toContain("sessionStorage.setItem('prazosVencidosDismissed', '1')");
  expect(template).toContain('href="{{ PREFIX }}/integrations"');
  expect(template).toContain('href="{{ PREFIX }}/oauth/pdpj/connect"');
  expect(template).toContain('sem expor segredo');

  await page.setContent(`
    <main>
      <div id="controladoriaApiSummary">
        <strong id="ctrlApiProvider">Aguardando busca</strong>
        <span id="ctrlApiStatus" class="badge bg-secondary">idle</span>
        <span id="ctrlApiReason">Abra Buscar Intimacoes para validar PDPJ.</span>
        <div data-testid="controladoria-api-actions">
          <button type="button">Buscar subsidiarias</button>
          <a href="/casehub/integrations">Ver integracoes</a>
          <a href="/casehub/oauth/pdpj/connect">Conectar PDPJ</a>
        </div>
      </div>
      <div id="intimacoesApiStatus">
        <strong id="intimacoesApiProvider">Aguardando busca</strong>
        <span id="intimacoesApiProviderStatus" class="badge bg-secondary">idle</span>
        <span id="intimacoesApiGrant">-</span>
        <span id="intimacoesApiLastAttempt">-</span>
        <span id="intimacoesApiReason">A busca ainda nao foi executada.</span>
        <div id="intimacoesApiErrorWrap" class="d-none"><code id="intimacoesApiError"></code></div>
        <details id="intimacoesApiChainWrap" class="d-none"><ul id="intimacoesApiChain"></ul></details>
      </div>
    </main>
  `);

  await expect(page.locator('#controladoriaApiSummary')).toContainText('Aguardando busca');
  await expect(page.getByTestId('controladoria-api-actions')).toContainText('Buscar subsidiarias');
  await expect(page.getByTestId('controladoria-api-actions')).toContainText('Conectar PDPJ');
  await expect(page.locator('#intimacoesApiStatus')).toContainText('Aguardando busca');
});
