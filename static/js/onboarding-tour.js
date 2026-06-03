/**
 * CaseHub Lite - Onboarding Tour (Enhanced)
 * Uses Shepherd.js for step-by-step guided tutorial
 * All text in Portuguese (pt-BR)
 * Features: modal overlay, progress indicator, expanded coverage
 */

function startOnboardingTour() {
    if (localStorage.getItem('casehub_tour_done')) return;
    if (document.body && document.body.classList.contains('casehub-browser-basic')) return;
    if (typeof Shepherd === 'undefined') return;

    var totalSteps = 20;

    function progressHTML(stepNum) {
        return '<div class="casehub-tour-progress-bar">' +
            '<span class="tour-progress-text">Passo ' + stepNum + ' de ' + totalSteps + '</span>' +
            '<div class="tour-progress-track">' +
            '<div class="tour-progress-fill" style="width:' + Math.round((stepNum / totalSteps) * 100) + '%"></div>' +
            '</div></div>';
    }

    function expandSection(sectionId) {
        return function() {
            return new Promise(function(resolve) {
                var items = document.getElementById(sectionId);
                if (items) items.style.maxHeight = '500px';
                setTimeout(resolve, 300);
            });
        };
    }

    var tour = new Shepherd.Tour({
        useModalOverlay: true,
        defaultStepOptions: {
            classes: 'casehub-tour-step',
            scrollTo: { behavior: 'smooth', block: 'center' },
            cancelIcon: { enabled: true },
            modalOverlayOpeningPadding: 8,
            modalOverlayOpeningRadius: 8,
            buttons: [
                { text: 'Pular Tour', action: function() { this.complete(); }, classes: 'shepherd-button-secondary' },
                { text: 'Voltar', action: function() { this.back(); }, classes: 'shepherd-button-secondary' },
                { text: 'Proximo', action: function() { this.next(); }, classes: 'shepherd-button-primary' }
            ]
        }
    });

    // Step 1: Welcome (no attachment)
    tour.addStep({
        id: 'welcome',
        title: 'Bem-vindo ao CaseHub! &#9878;',
        text: progressHTML(1) +
            '<p>Este e o seu sistema de gestao juridica completo. Vamos fazer um tour pelas principais funcionalidades para voce comecar a usar com confianca.</p>' +
            '<p style="font-size:13px;color:var(--text-secondary);">O tour leva cerca de 3 minutos.</p>',
        buttons: [
            { text: 'Pular Tour', action: function() { this.complete(); }, classes: 'shepherd-button-secondary' },
            { text: 'Comecar', action: function() { this.next(); }, classes: 'shepherd-button-primary' }
        ]
    });

    // Step 2: Sidebar navigation
    tour.addStep({
        id: 'sidebar',
        title: 'Navegacao',
        text: progressHTML(2) +
            '<p>A barra lateral e o menu principal. Clique nas categorias para expandir os submenus. Em telas menores, use o icone de hamburger para abrir.</p>' +
            '<p class="tour-cta"><strong>Dica:</strong> Os itens sao organizados por area: Gestao, Comunicacao, Juridico, IA e Admin.</p>',
        attachTo: { element: '.sidebar', on: 'right' }
    });

    // Step 3: Dashboard / Painel
    tour.addStep({
        id: 'dashboard',
        title: 'Painel Principal',
        text: progressHTML(3) +
            '<p>Seu painel de controle com resumo do escritorio: processos ativos, tarefas pendentes, faturamento e indicadores em tempo real.</p>' +
            '<p class="tour-cta"><strong>Dica:</strong> Arraste os widgets para reorganizar o layout do jeito que preferir.</p>',
        attachTo: { element: '.sidebar a[href*="/dashboard"]', on: 'right' }
    });

    // Step 4: Clientes
    tour.addStep({
        id: 'clients',
        title: 'Gestao de Clientes',
        text: progressHTML(4) +
            '<p>Cadastre e gerencie todos os clientes do escritorio. Cada ficha tem dados de contato, documentos, processos vinculados e historico financeiro.</p>' +
            '<p class="tour-cta"><strong>Clique aqui para experimentar:</strong> Acesse Clientes e clique em "+ Novo Cliente" para criar o primeiro cadastro.</p>',
        attachTo: { element: '.sidebar a[href*="/clients"]', on: 'right' }
    });

    // Step 5: How to create a client (tips)
    tour.addStep({
        id: 'clients-howto',
        title: 'Como Cadastrar um Cliente',
        text: progressHTML(5) +
            '<p>Para criar um novo cliente:</p>' +
            '<ol style="padding-left:18px;margin:8px 0;">' +
            '<li>Clique em <strong>"+ Novo Cliente"</strong> no topo da pagina</li>' +
            '<li>Preencha nome, CPF/CNPJ, e-mail e telefone</li>' +
            '<li>Adicione tags para categorizar (ex: "trabalhista", "VIP")</li>' +
            '<li>Clique em <strong>"Salvar"</strong></li>' +
            '</ol>' +
            '<p class="tour-cta">Depois, voce pode vincular processos e documentos a esse cliente.</p>',
        attachTo: { element: '.sidebar a[href*="/clients"]', on: 'right' }
    });

    // Step 6: Processos
    tour.addStep({
        id: 'cases',
        title: 'Processos',
        text: progressHTML(6) +
            '<p>Controle todos os processos com numero CNJ, status, prazos e movimentacoes. O sistema cria checklists automaticos ao cadastrar.</p>' +
            '<p class="tour-cta"><strong>Clique aqui para experimentar:</strong> Crie um processo e vincule a um cliente existente.</p>',
        attachTo: { element: '.sidebar a[href*="/cases"]', on: 'right' }
    });

    // Step 7: How to create a process
    tour.addStep({
        id: 'cases-howto',
        title: 'Como Cadastrar um Processo',
        text: progressHTML(7) +
            '<p>Para criar um novo processo:</p>' +
            '<ol style="padding-left:18px;margin:8px 0;">' +
            '<li>Clique em <strong>"+ Novo Processo"</strong></li>' +
            '<li>Informe o numero CNJ (validado automaticamente)</li>' +
            '<li>Selecione o cliente, tipo de acao e vara</li>' +
            '<li>O sistema gera checklists e prazos iniciais</li>' +
            '</ol>' +
            '<p class="tour-cta">Use a Consulta Tribunal para importar dados automaticamente pelo CNJ.</p>',
        attachTo: { element: '.sidebar a[href*="/cases"]', on: 'right' }
    });

    // Step 8: Documentos
    tour.addStep({
        id: 'documents',
        title: 'Documentos',
        text: progressHTML(8) +
            '<p>Armazene peticoes, contratos e procuracoes. Faca upload arrastando arquivos, organize por categorias e vincule a clientes e processos.</p>' +
            '<p class="tour-cta">Suporta preview de PDF e imagens direto no navegador.</p>',
        attachTo: { element: '.sidebar a[href*="/documents"]', on: 'right' }
    });

    // Step 9: Tarefas (Kanban)
    tour.addStep({
        id: 'tasks',
        title: 'Tarefas (Kanban)',
        text: progressHTML(9) +
            '<p>Gerencie tarefas em um quadro Kanban: arraste cartoes entre colunas "A Fazer", "Em Progresso", "Revisao" e "Concluido".</p>' +
            '<p class="tour-cta"><strong>Clique aqui para experimentar:</strong> Crie sua primeira tarefa e atribua um prazo.</p>',
        attachTo: { element: '.sidebar a[href*="/tasks"]', on: 'right' }
    });

    // Step 10: How to use Kanban
    tour.addStep({
        id: 'tasks-howto',
        title: 'Como Usar o Kanban',
        text: progressHTML(10) +
            '<p>O Kanban e visual e intuitivo:</p>' +
            '<ul style="padding-left:18px;margin:8px 0;">' +
            '<li><strong>Arrastar cartoes</strong> entre colunas atualiza o status</li>' +
            '<li>Adicione <strong>subtarefas</strong> para dividir trabalhos grandes</li>' +
            '<li>Use <strong>tags coloridas</strong> para prioridade (Baixa, Media, Alta, Urgente)</li>' +
            '<li>Vincule tarefas a processos para rastreabilidade</li>' +
            '</ul>' +
            '<p class="tour-cta">Alterne entre visao Kanban, Lista e Calendario.</p>',
        attachTo: { element: '.sidebar a[href*="/tasks"]', on: 'right' }
    });

    // Step 11: Agenda
    tour.addStep({
        id: 'calendar',
        title: 'Agenda',
        text: progressHTML(11) +
            '<p>Visualize audiencias, reunioes e prazos em calendario mensal, semanal ou diario. Integra com Google Calendar para notificacoes no celular.</p>',
        attachTo: { element: '.sidebar a[href*="/calendar"]', on: 'right' }
    });

    // Step 12: E-mails
    tour.addStep({
        id: 'emails',
        title: 'E-mails',
        text: progressHTML(12) +
            '<p>Envie e receba e-mails diretamente pelo sistema. Configure sua conta IMAP e use templates prontos para comunicacoes frequentes.</p>' +
            '<p class="tour-cta">E-mails sao vinculados automaticamente aos clientes pelo endereco.</p>',
        attachTo: { element: '.sidebar a[href*="/emails"]', on: 'right' }
    });

    // Step 13: Faturamento
    tour.addStep({
        id: 'billing',
        title: 'Faturamento',
        text: progressHTML(13) +
            '<p>Controle honorarios, registre tempo trabalhado, gere faturas em R$ e acompanhe pagamentos. Visao completa da saude financeira.</p>',
        attachTo: { element: '.sidebar a[href*="/billing"]', on: 'right' }
    });

    // Step 14: Controladoria
    tour.addStep({
        id: 'controladoria',
        title: 'Controladoria Juridica',
        text: progressHTML(14) +
            '<p>Painel centralizado de prazos processuais, intimacoes e indicadores de desempenho. Exporte tudo para Excel.</p>' +
            '<p class="tour-cta"><strong>Essencial:</strong> Configure aqui o monitoramento de prazos para nunca perder um vencimento.</p>',
        attachTo: { element: '.sidebar a[href*="/controladoria"]', on: 'right' },
        beforeShowPromise: expandSection('juridico-items')
    });

    // Step 15: Ferramentas (Calculadoras)
    tour.addStep({
        id: 'tools',
        title: 'Ferramentas (33 Calculadoras)',
        text: progressHTML(15) +
            '<p>Calculadoras juridicas para todas as areas:</p>' +
            '<ul style="padding-left:18px;margin:8px 0;font-size:13px;">' +
            '<li><strong>Trabalhista:</strong> Rescisao, horas extras, seguro-desemprego</li>' +
            '<li><strong>Civel:</strong> Correcao monetaria, juros, honorarios</li>' +
            '<li><strong>Criminal:</strong> Dosimetria, progressao, prescricao</li>' +
            '<li><strong>Previdenciario, Tributario, Bancario</strong></li>' +
            '</ul>' +
            '<p class="tour-cta"><strong>Clique aqui para experimentar:</strong> Teste uma calculadora e exporte o resultado em PDF.</p>',
        attachTo: { element: '.sidebar a[href*="/tools"]', on: 'right' },
        beforeShowPromise: expandSection('juridico-items')
    });

    // Step 16: Pecas Processuais
    tour.addStep({
        id: 'pecas',
        title: 'Pecas Processuais',
        text: progressHTML(16) +
            '<p>Gere peticoes, contestacoes, recursos e contratos com auxilio de IA. Exporte em DOCX para edicao final.</p>' +
            '<p class="tour-cta">Vincule ao processo para preenchimento automatico dos dados das partes.</p>',
        attachTo: { element: '.sidebar a[href*="/pecas"]', on: 'right' },
        beforeShowPromise: expandSection('juridico-items')
    });

    // Step 17: Maestro IA
    tour.addStep({
        id: 'maestro',
        title: 'Maestro IA',
        text: progressHTML(17) +
            '<p>Seu assistente de inteligencia artificial juridica. Pergunte sobre legislacao, peca ajuda em pecas processuais, ou peca resumos de documentos.</p>' +
            '<p class="tour-cta"><strong>Clique aqui para experimentar:</strong> Abra o Maestro e pergunte "Quais prazos vencem esta semana?"</p>',
        attachTo: { element: '.sidebar a[href*="/assistente"]', on: 'right' },
        beforeShowPromise: expandSection('ia-items')
    });

    // Step 18: CRM / Leads
    tour.addStep({
        id: 'leads',
        title: 'CRM (Leads)',
        text: progressHTML(18) +
            '<p>Gerencie potenciais clientes em um funil de vendas: de "Novo Contato" ate "Convertido". O scoring automatico prioriza os leads mais promissores.</p>',
        attachTo: { element: '.sidebar a[href*="/leads"]', on: 'right' },
        beforeShowPromise: expandSection('ia-items')
    });

    // Step 19: Manual
    tour.addStep({
        id: 'manual',
        title: 'Manual Completo',
        text: progressHTML(19) +
            '<p>Para instrucoes detalhadas sobre qualquer funcionalidade, acesse o <strong>Manual</strong> na sidebar. Ele cobre todas as 23 areas do sistema com passo-a-passo.</p>',
        attachTo: { element: '.sidebar a[href*="/manual"]', on: 'right' }
    });

    // Step 20: Settings / Finish
    tour.addStep({
        id: 'settings',
        title: 'Configuracoes e Proximo Passo',
        text: progressHTML(20) +
            '<p>Personalize o sistema com o logo e as cores do escritorio em <strong>Configuracoes</strong>. Gerencie usuarios e permissoes em <strong>Admin</strong>.</p>' +
            '<p style="margin-top:12px;padding:10px;background:rgba(28, 36, 71,0.1);border-radius:8px;font-size:13px;">' +
            '<strong>Proximo passo sugerido:</strong> Cadastre seu primeiro cliente e crie um processo para experimentar o fluxo completo.</p>',
        attachTo: { element: '.sidebar a[href*="/settings"]', on: 'right' },
        beforeShowPromise: expandSection('admin-items'),
        buttons: [
            { text: 'Voltar', action: function() { this.back(); }, classes: 'shepherd-button-secondary' },
            { text: 'Concluir Tour', action: function() { this.complete(); }, classes: 'shepherd-button-primary' }
        ]
    });

    // Mark tour as done on complete or cancel
    tour.on('complete', function() {
        localStorage.setItem('casehub_tour_done', 'true');
    });
    tour.on('cancel', function() {
        localStorage.setItem('casehub_tour_done', 'true');
    });

    tour.start();
}

// Auto-start on first visit to dashboard
document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname.includes('/dashboard')) {
        setTimeout(startOnboardingTour, 1000);
    }
});
