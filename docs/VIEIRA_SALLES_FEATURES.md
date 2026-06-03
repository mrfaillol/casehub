# CaseHub Lite — Features o cliente (Baseado na Auditoria Lovable)

## O que eles tentaram fazer no Lovable (e falharam)

### 1. Controle de Prazos (Prazo Certo V2)
**O que tinham:**
- 4 cards: Total Prazos, Fatais Hoje, Proximos Vencimento, Concluidos
- Buscar Intimacoes (modal com periodo, MAS sem API real de tribunal)
- Novo Prazo (modal: cliente, parte contraria, processo CNJ, responsavel, data publicacao, prazo em dias uteis, tipo, descricao)
- Exportar Excel
- Filtros por mes e status
- Busca por cliente/parte/processo

**O que CaseHub Lite ja tem de SUPERIOR:**
- Calculadora de prazos CPC com feriados de 27 UFs
- Recesso judicial automatico (20/dez a 20/jan)
- 16 tipos de prazo CPC com referencia legal
- Prazo em dobro (Art. 229 CPC)
- DataJud API client (consulta REAL a tribunais)
- Escavador API client (monitoramento + publicacoes DJE)
- JusBrasil API client (webhooks real-time)

**O que FALTA implementar:**
- [ ] Dashboard de controladoria com os 4 cards que eles tinham
- [ ] Modal de novo prazo vinculado a processo existente
- [ ] Exportar Excel de prazos
- [ ] Busca de intimacoes via API real (DataJud/Escavador)
- [ ] Notificacao automatica 3 dias antes do vencimento
- [ ] Atribuicao de prazo a colaborador especifico

### 2. Tabela de Processos
**O que tinham:**
- Colunas: N. Processo, Cliente, Parte Contraria, Tribunal, Setor, Tipo, Status, Data Fim
- Badges de status coloridos
- Botao + Novo Processo

**O que CaseHub Lite ja tem de SUPERIOR:**
- 15+ campos (CPF/CNPJ, OAB, vara, comarca, fase processual, polo ativo/passivo)
- Validacao formato CNJ
- Busca por tribunal via DataJud

**O que FALTA:**
- [ ] Badges de status coloridos na lista (verde/amarelo/vermelho)
- [ ] Coluna "Data Fim" visivel na lista
- [ ] Setor do processo (previdenciario, trabalhista, civel, familia)

### 3. Dashboard de Indices (Analytics)
**O que tinham (e era BOM):**
- Tempo Medio por Setor (barras)
- Tempo Medio por Tipo (barras horizontais)
- Indice de Vitoria por Setor (%)
- Indice de Vitoria por Tipo (%)
- Processos por Mes (linha temporal)
- Distribuicao por Setor ao Longo do Tempo (stacked bar)
- Filtros: setor, tipo, periodo

**O que CaseHub Lite tem:**
- Dashboard basico com stat cards
- Grafico de tendencia (ultimos 6 meses)

**O que FALTA (replicar os 6 graficos deles):**
- [ ] Indice de vitoria por setor e por tipo
- [ ] Tempo medio de processo por setor
- [ ] Distribuicao por setor ao longo do tempo
- [ ] Marcar processo como vitoria/derrota/acordo
- [ ] Filtros por setor, tipo e periodo

### 4. Funcionalidades que eles PEDIRAM na reuniao (mas nao tinham)
- [ ] Agenda integrada com Google Agendas (substituir Trello)
- [ ] Kanban por colaborador (ja temos kanban, falta filtro por pessoa)
- [ ] CRM comercial (ja temos leads, precisa adaptar pipeline BR)
- [ ] Portal do cliente (ja temos, precisa adaptar para BR)
- [ ] Multi-sede na nuvem (ja temos, VPS Oracle)
- [ ] IA para processar documentos (Maestro Lite — planejado)

### 5. Calculadora de Rescisao
**O que tinham (app separado):**
- Formulario completo de rescisao trabalhista
- Progressao salarial com multiplos periodos
- Verbas adicionais (horas extras, adicional noturno, etc.)

**Implementar no CaseHub Lite como modulo de /tools:**
- [ ] Calculadora de rescisao trabalhista
- [ ] Calculadora de verbas previdenciarias
- [ ] Gerador de pecas processuais

## Prioridade de Implementacao (Fase 1 — Controladoria)

1. Dashboard de controladoria com 4 cards de prazos
2. Modal de novo prazo vinculado a processo
3. Busca de intimacoes via DataJud (API real)
4. 6 graficos de indices (replicar Lovable mas melhor)
5. Kanban de tarefas filtrado por colaborador
6. Google Calendar sync funcional
