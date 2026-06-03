"""Release notice content for short-lived CaseHub Basic announcements."""

from config import settings


def get_casehub_release_notice() -> dict:
    """Return the current user-facing release notice payload."""
    return {
        "enabled": settings.CASEHUB_RELEASE_NOTICE_ENABLED,
        "id": settings.CASEHUB_RELEASE_NOTICE_ID,
        "title": "Atualizacao CaseHub - 04/05",
        "eyebrow": "Comunicado rapido",
        "intro": (
            "Esta atualizacao deixa a rotina do CaseHub mais clara para o uso do escritorio "
            "enquanto a conexao oficial PDPJ/CNJ e finalizada."
        ),
        "pdpj_title": "O que aconteceu com a busca PDPJ/CNJ",
        "pdpj_items": [
            (
                "A busca automatica de prazos por OAB depende de uma autorizacao oficial "
                "PDPJ/CNJ valida para consultar os sistemas do CNJ em nome do escritorio."
            ),
            (
                "A autorizacao atual nao esta completa para essa consulta automatica. Por isso, "
                "o CaseHub passou a avisar que a conexao esta pendente em vez de mostrar uma "
                "tabela vazia como se tivesse consultado corretamente."
            ),
            (
                "Isso nao significa perda de dados internos. Significa apenas que a captura "
                "automatica de prazos diretamente do CNJ ainda precisa da conexao externa correta."
            ),
        ],
        "fallback_title": "O escritorio continua suprido?",
        "fallback_body": (
            "Sim, para a operacao imediata. Dashboard, agenda, clientes, CRM, tarefas, Kanban "
            "e controle manual de prazos continuam disponiveis. Enquanto a conexao PDPJ/CNJ nao "
            "for concluida, os prazos novos devem ser conferidos e registrados pelo fluxo interno "
            "do escritorio, sem depender da puxada automatica por OAB."
        ),
        "patch_title": "Patch notes para usuarios",
        "patch_notes": [
            "Painel inicial renovado com visao do dia, tarefas, prazos, equipe, atividade recente e casos recentes.",
            "Agenda Google simplificada: conexao por botao Entrar com Google e nomes neutros de agenda.",
            "Controladoria mais clara: quando o PDPJ/CNJ nao esta autorizado, o sistema informa a pendencia diretamente.",
            "CRM, Clientes, Agenda e Kanban receberam ajustes visuais de espacamento, responsividade e leitura.",
            "Busca de prazos por OAB agora evita falso resultado: se a conexao oficial nao estiver pronta, o usuario ve o motivo.",
            "Base Basic preparada para ciclos rapidos de beta test ao longo desta semana.",
        ],
        "victor_title": "Mensagem do Victor",
        "victor_message": (
            "Pessoal, esta versao ja permite trabalhar com dashboard, agenda, clientes, CRM, tarefas, "
            "Kanban e acompanhamento interno de prazos. A parte que ainda depende de autorizacao externa "
            "e a puxada automatica PDPJ/CNJ por OAB. Ao longo desta semana esta versao sera fortemente "
            "enriquecida como beta test, com ajustes guiados pelo uso real do escritorio."
        ),
        "cta_label": "Entendi",
    }
