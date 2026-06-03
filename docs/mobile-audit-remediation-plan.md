# Auditoria e Correções Mobile — CaseHub (Produção)

## Objetivo
Padronizar e corrigir a experiência mobile entre os ambientes:

- `https://app.example.com`
- `https://cliente.example.com`

com foco em performance, UX e paridade de release/configuração.

## Escopo técnico da auditoria

### 1) Paridade entre ambientes
- Validar mesmo SHA/versão de build em ambos os domínios.
- Comparar variáveis de ambiente, feature flags, CDN/cache e headers HTTP.
- Verificar divergências de assets (404 de chunks, hashes inconsistentes, compressão ausente).

### 2) Core Web Vitals e performance mobile
- Medir e comparar LCP, INP, CLS e TTFB por rota crítica.
- Executar Lighthouse (3 execuções por rota), PageSpeed Insights e WebPageTest.
- Coletar waterfall, filmstrip, JS coverage e long tasks no Chrome DevTools.

### 3) Lazy load e estratégia de renderização
- Corrigir lazy loading de elementos acima da dobra (above-the-fold).
- Garantir preload do CSS crítico e do recurso principal da primeira dobra.
- Revisar code splitting para reduzir bundle inicial e bloquear menos a thread principal.

### 4) Assets e payload
- Ajustar imagens (WebP/AVIF, `srcset`, tamanhos corretos, lazy load somente abaixo da dobra).
- Otimizar fontes (subset, preload apenas crítico, `font-display`).
- Reduzir scripts de terceiros e adiar execução não crítica.

### 5) UX e estabilidade mobile
- Validar fluxos principais em Android/Chrome e iOS/Safari.
- Corrigir layout shifts, flicker, travamentos e inconsistências de toque/scroll.
- Correlacionar erros JS de produção com sessões lentas.

## Plano de correção por ondas

### Onda 1 — Hotfix (24–48h)
1. Remover lazy load de conteúdo acima da dobra.
2. Garantir preload de CSS crítico e imagem principal.
3. Corrigir assets quebrados/chunks com cache inválido.
4. Mitigar scripts bloqueantes no carregamento inicial.

### Onda 2 — Estabilização (1 sprint)
1. Rebalancear code splitting por rota.
2. Reduzir payload inicial JS/CSS e imagens em rotas prioritárias.
3. Ajustar fontes e third-parties para reduzir INP e TBT.

### Onda 3 — Hardening (2+ sprints)
1. Instituir budgets de performance no CI.
2. Monitorar CWV em produção por domínio/rota.
3. Automatizar regressão mobile em rotas críticas.

## Critérios de aceite
- Paridade mobile comprovada entre ambos os domínios.
- Rotas críticas com metas mínimas:
  - LCP < 2.5s
  - INP < 200ms
  - CLS < 0.1
- Sem regressão visual/funcional em Android e iOS.
- Evidências anexas: relatório por rota, perf traces e checklist de validação.

## Entregáveis
- Relatório técnico com severidade, causa raiz e correção proposta.
- Backlog priorizado (Hotfix / Estabilização / Hardening).
- Evidências de re-teste pós-correção em ambos os domínios.
