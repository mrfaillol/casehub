/**
 * CaseHub Basic — Onboarding Tour (Cláusula 2.1 focused, 8 steps)
 *
 * Focado nos 4 módulos canônicos do Plano Basic:
 *   Controladoria, Tarefas (Kanban), Clientes, Processos, Agenda.
 *
 * Tema visual: neuromorphic+tabs+dock (não a sidebar legacy).
 * Selectors flexíveis: tenta .ch-tabs / .ch-bottomnav primeiro, cai para
 * `a[href*="..."]` genérico. Se um anchor não existir, o step roda
 * sem attach (modal central) em vez de quebrar.
 *
 * Progresso persiste no DB via /api/onboarding/tour-step e
 * /api/onboarding/tour-complete (lê window.casehubUser para estado inicial).
 */
(function () {
    "use strict";

    var u = window.casehubUser || null;

    // Gate: se já completou, não inicia automaticamente. Só roda se chamado
    // explicitamente via startCasehubBasicTour() (botão "Iniciar tour" no menu Ajuda).
    function shouldAutoStart() {
        if (!u) return false;
        if (u.onboarding_completed_at) return false;
        if (typeof Shepherd === "undefined") return false;
        return true;
    }

    var PREFIX = (u && u.prefix) || "";
    var totalSteps = 8;

    function progress(stepNum) {
        var pct = Math.round((stepNum / totalSteps) * 100);
        return (
            '<div class="ch-tour-progress" aria-hidden="true">' +
            '<span class="ch-tour-progress__label">Passo ' + stepNum + " de " + totalSteps + "</span>" +
            '<div class="ch-tour-progress__track">' +
            '<div class="ch-tour-progress__fill" style="width:' + pct + '%"></div>' +
            "</div></div>"
        );
    }

    // Tenta múltiplos selectors até encontrar um elemento; retorna selector ou null.
    function firstMatch(selectors) {
        for (var i = 0; i < selectors.length; i++) {
            var el = document.querySelector(selectors[i]);
            if (el) return selectors[i];
        }
        return null;
    }

    function persistStep(stepId) {
        if (!u || u.demo) return;  // skip telemetry in demo/preview
        try {
            fetch(PREFIX + "/api/onboarding/tour-step", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ step_id: stepId }),
                keepalive: true,
            }).catch(function () {/* silent */});
        } catch (e) {/* silent */}
    }

    function persistComplete() {
        if (!u || u.demo) return;
        try {
            fetch(PREFIX + "/api/onboarding/tour-complete", {
                method: "POST",
                credentials: "same-origin",
                keepalive: true,
            }).catch(function () {/* silent */});
        } catch (e) {/* silent */}
    }

    function buildTour() {
        var tour = new Shepherd.Tour({
            useModalOverlay: true,
            defaultStepOptions: {
                classes: "ch-tour-step ch-tour-step--basic",
                scrollTo: { behavior: "smooth", block: "center" },
                cancelIcon: { enabled: true },
                modalOverlayOpeningPadding: 8,
                modalOverlayOpeningRadius: 10,
                buttons: [
                    { text: "Pular tour", action: function () { this.complete(); }, classes: "ch-tour-btn ch-tour-btn--ghost" },
                    { text: "Voltar", action: function () { this.back(); }, classes: "ch-tour-btn ch-tour-btn--ghost" },
                    { text: "Próximo", action: function () { this.next(); }, classes: "ch-tour-btn ch-tour-btn--primary" }
                ]
            }
        });

        // 1. Welcome
        tour.addStep({
            id: "welcome",
            title: "Bem-vindo ao CaseHub, " + (u && u.name ? u.name : "advogado") + "!",
            text: progress(1) +
                "<p>Esse tour mostra como usar os módulos essenciais do seu Plano Basic em cerca de 2 minutos. Você pode pular a qualquer momento — voltamos do menu Ajuda.</p>",
            buttons: [
                { text: "Pular tour", action: function () { this.complete(); }, classes: "ch-tour-btn ch-tour-btn--ghost" },
                { text: "Começar", action: function () { this.next(); }, classes: "ch-tour-btn ch-tour-btn--primary" }
            ]
        });

        // 2. Navegação (tabs/dock)
        var navSel = firstMatch([".ch-tabs-wrap", ".ch-bottomnav-wrap", ".sidebar", "nav"]);
        tour.addStep({
            id: "navigation",
            title: "Sua navegação",
            text: progress(2) +
                "<p>No <strong>desktop</strong>, as abas no topo te levam aos módulos. No <strong>celular</strong>, use a barra de ícones embaixo. Os 4 módulos do seu Plano Basic estão aqui: Controladoria, Agenda, Tarefas e Processos.</p>",
            attachTo: navSel ? { element: navSel, on: "bottom" } : undefined
        });

        // 3. Controladoria
        var controlSel = firstMatch([
            '.ch-bottomnav__item[href*="/controladoria"]',
            '.ch-tabs__tab[href*="/controladoria"]',
            'a[href*="/controladoria"]'
        ]);
        tour.addStep({
            id: "controladoria",
            title: "Controladoria — prazos sob controle",
            text: progress(3) +
                "<p>Aqui você acompanha <strong>prazos processuais</strong> em tempo real, importados automaticamente pela ComunicaAPI do CNJ.</p>" +
                "<p>As cores indicam urgência: <span style='color:#44bb44;'>verde</span> = no prazo, <span style='color:#d4a017;'>amarelo</span> = vencendo essa semana, <span style='color:#d04949;'>vermelho</span> = vencendo em 2 dias ou menos.</p>",
            attachTo: controlSel ? { element: controlSel, on: "top" } : undefined
        });

        // 4. Agenda
        var calSel = firstMatch([
            '.ch-bottomnav__item[href*="/calendar"]',
            '.ch-tabs__tab[href*="/calendar"]',
            'a[href*="/calendar"]'
        ]);
        tour.addStep({
            id: "agenda",
            title: "Agenda — audiências, reuniões, prazos",
            text: progress(4) +
                "<p>Sua agenda unificada. Eventos podem ser <strong>sincronizados com o Google Calendar</strong> para chegar no seu celular automaticamente. Todo evento pode ser vinculado a um processo ou cliente.</p>",
            attachTo: calSel ? { element: calSel, on: "top" } : undefined
        });

        // 5. Tarefas Kanban
        var tasksSel = firstMatch([
            '.ch-bottomnav__item[href*="/tasks"]',
            '.ch-tabs__tab[href*="/tasks"]',
            'a[href*="/tasks/kanban"]',
            'a[href*="/tasks"]'
        ]);
        tour.addStep({
            id: "tarefas",
            title: "Tarefas — Kanban visual",
            text: progress(5) +
                "<p>Um quadro Kanban com colunas <em>A Fazer → Em Progresso → Revisão → Concluído</em>. <strong>Arraste</strong> os cards para mudar de status. Cada tarefa pode ter prazo, subtarefas e estar vinculada a um processo.</p>",
            attachTo: tasksSel ? { element: tasksSel, on: "top" } : undefined
        });

        // 6. Clientes
        var clientsSel = firstMatch([
            '.ch-bottomnav__item[href*="/clients"]',
            '.ch-tabs__tab[href*="/clients"]',
            'a[href*="/clients"]'
        ]);
        tour.addStep({
            id: "clientes",
            title: "Clientes — PF e PJ",
            text: progress(6) +
                "<p>Cadastre <strong>pessoa física</strong> ou <strong>pessoa jurídica</strong> com CPF/CNPJ validado, dados de contato e documentos. Cada cliente concentra o histórico financeiro, processos e tarefas vinculadas.</p>",
            attachTo: clientsSel ? { element: clientsSel, on: "top" } : undefined
        });

        // 7. Processos
        var casesSel = firstMatch([
            '.ch-bottomnav__item[href*="/cases"]',
            '.ch-tabs__tab[href*="/cases"]',
            'a[href*="/cases"]'
        ]);
        tour.addStep({
            id: "processos",
            title: "Processos — import automático CNJ",
            text: progress(7) +
                "<p>Cadastre processos pelo <strong>número CNJ</strong>. O sistema valida o número, importa dados via DataJud e cria checklists/prazos automaticamente. Você só preenche o que falta.</p>",
            attachTo: casesSel ? { element: casesSel, on: "top" } : undefined
        });

        // 8. Próximos passos
        tour.addStep({
            id: "next",
            title: "Pronto! Hora de usar",
            text: progress(8) +
                "<p>Próximos passos sugeridos:</p>" +
                "<ol style='padding-left:18px;margin:8px 0;'>" +
                "<li>Cadastre seu primeiro <strong>cliente</strong></li>" +
                "<li>Crie um <strong>processo</strong> com número CNJ — o sistema importa o resto</li>" +
                "<li>Veja os <strong>prazos</strong> aparecerem na Controladoria</li>" +
                "</ol>" +
                "<p style='margin-top:10px;font-size:.88em;opacity:.85;'>Você pode rever esse tour a qualquer momento em <strong>Ajuda → Iniciar tour</strong>.</p>",
            buttons: [
                { text: "Voltar", action: function () { this.back(); }, classes: "ch-tour-btn ch-tour-btn--ghost" },
                { text: "Vamos começar", action: function () { this.complete(); }, classes: "ch-tour-btn ch-tour-btn--primary" }
            ]
        });

        // Track step transitions for DB persistence + recovery
        tour.on("show", function (e) {
            try {
                var stepId = e && e.step && e.step.id ? e.step.id : null;
                if (stepId) persistStep(stepId);
            } catch (err) {/* silent */}
        });
        tour.on("complete", function () { persistComplete(); });
        tour.on("cancel", function () { persistComplete(); });

        return tour;
    }

    function startCasehubBasicTour(opts) {
        opts = opts || {};
        if (typeof Shepherd === "undefined") {
            console.warn("[casehub-tour-basic] Shepherd not loaded");
            return;
        }
        var tour = buildTour();
        // Resume at last saved step if requested
        if (opts.resume && u && u.onboarding_tour_step) {
            var idx = tour.steps.findIndex(function (s) { return s.id === u.onboarding_tour_step; });
            if (idx >= 0) {
                tour.start();
                tour.show(idx);
                return;
            }
        }
        tour.start();
    }

    // Expose for "Iniciar tour" menu link
    window.startCasehubBasicTour = startCasehubBasicTour;

    // Auto-start on first visit to dashboard
    document.addEventListener("DOMContentLoaded", function () {
        if (!shouldAutoStart()) return;
        var path = window.location.pathname || "";
        if (path.indexOf("/dashboard") === -1 && path !== "/" && path !== PREFIX + "/") return;
        // Small delay so the page paints first
        setTimeout(function () { startCasehubBasicTour({ resume: true }); }, 900);
    });
})();
