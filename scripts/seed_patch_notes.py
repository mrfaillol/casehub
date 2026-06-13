#!/usr/bin/env python3
"""
CaseHub - Patch Notes Seeder

Insere as notas de atualização recentes (patch notes / hotfixes) como
Notification(notification_type='hotfix') para cada usuário da organização.
Essas notas alimentam a página "Novidades e atualizações"
(templates/app/notifications/hotfix.html), que é filtrada por user_id + org_id.

Idempotente: para cada usuário, só cria a nota se ainda não existir uma
hotfix com o mesmo título (idempotency key = (user_id, notification_type,
title)). Rodar de novo não duplica; se o texto de uma nota já existente for
corrigido, atualiza a mensagem e marca como não lida novamente.

Uso:
    python scripts/seed_patch_notes.py             # todas as orgs
    python scripts/seed_patch_notes.py --org-slug demo
    python scripts/seed_patch_notes.py --org-id 1
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import get_db, init_db, User, Notification
from models.tenant import Organization


# ---------------------------------------------------------------------------
# Patch notes — linguagem leiga (o que o usuário percebe, não jargão técnico).
# A ordem aqui é a ordem cronológica; o feed exibe do mais recente pro mais
# antigo (order_by created_at desc), e como criamos em sequência, o último
# da lista fica no topo.
# ---------------------------------------------------------------------------

PATCH_NOTES = [
    {
        "title": "Kanban com visual estilo Trello",
        "message": (
            "Os cartões do Kanban ganharam um novo visual inspirado no Trello: "
            "uma faixa colorida no topo identifica o responsável pela tarefa, "
            "o avatar aparece discretamente no rodapé ao lado do prazo, "
            "e o fundo branco torna a leitura mais limpa e confortável."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Maestro avisa automaticamente sobre prazos e tarefas",
        "message": (
            "O Maestro agora posta um resumo diário no chat da equipe toda manhã: "
            "prazos vencendo nos próximos 3 dias, tarefas atrasadas e compromissos "
            "do dia seguinte. Você não precisa mais buscar manualmente — "
            "o aviso chega sozinho."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Botão de entrar com Google de volta",
        "message": (
            "O acesso rápido com a conta Google voltou para a tela de login. "
            "Agora você pode entrar no CaseHub com um clique, sem precisar "
            "digitar e-mail e senha toda vez."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Painel com visual novo, mais leve e moderno",
        "message": (
            "O painel inicial ganhou um visual repaginado, com aquele acabamento "
            "suave e em relevo (neumórfico). Ficou mais bonito, mais confortável "
            "de ler e mais agradável no dia a dia."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Área de produtividade reorganizada",
        "message": (
            "Reorganizamos a área de produtividade para você encontrar as coisas "
            "mais rápido. Os atalhos e indicadores do dia a dia agora estão "
            "agrupados de um jeito mais lógico e fácil de usar."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Controladoria: prazos concluídos vão para Arquivados",
        "message": (
            "A controladoria agora tem duas abas: Ativos e Arquivados. "
            "Quando um prazo é marcado como Concluído ele sai da lista principal "
            "na hora e vai direto para Arquivados — sem precisar recarregar a página. "
            "De lá você pode reabrir o prazo ou excluí-lo."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Controladoria: novo status 'Aguarda Correção'",
        "message": (
            "O dropdown de status dos prazos ganhou a opção Aguarda Correção. "
            "Útil para marcar processos que precisam de revisão pelo advogado "
            "antes de seguir para Concluído."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Agenda: vários responsáveis por compromisso",
        "message": (
            "Agora é possível selecionar mais de um responsável em um compromisso. "
            "Ideal para audiências ou reuniões em que mais de um advogado precisa "
            "estar presente. A seleção fica em uma caixinha própria, sem depender "
            "de Ctrl ou Cmd para marcar mais de uma pessoa."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Agenda: campo de resultado por atendimento",
        "message": (
            "Cada compromisso agora tem um campo Resultado: Contrato Fechado, "
            "No Show, Follow-up ou Cancelado. "
            "Registre o desfecho direto no compromisso para acompanhar a "
            "conversão dos atendimentos sem precisar de planilha separada."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Envio de e-mail direto pelo CaseHub (Gmail)",
        "message": (
            "Agora é possível enviar e-mails diretamente pelo CaseHub usando a conta Gmail conectada. "
            "Um botão 'Email' aparece nas páginas de processo, tarefa e cliente — "
            "basta clicar para abrir o compositor e enviar sem sair do sistema. "
            "O Maestro também ganhou o mesmo botão no cabeçalho."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Caixa de entrada Gmail integrada",
        "message": (
            "A caixa de entrada do Gmail agora pode ser acessada diretamente pelo CaseHub "
            "em E-mails → Gmail. Visualize as mensagens recentes, veja remetente, assunto "
            "e vínculos com clientes e processos sem precisar abrir o Gmail separado."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Envio de documentos para o Google Drive",
        "message": (
            "Documentos anexados a processos agora têm um botão para enviar diretamente "
            "ao Google Drive do escritório. O arquivo é organizado automaticamente por "
            "cliente e fica disponível no Drive com um link salvo no CaseHub."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Correções de segurança — 11/06/2026",
        "message": (
            "Aplicamos uma série de correções internas de segurança que reforçam o "
            "isolamento entre organizações e protegem dados sensíveis. "
            "Nenhuma funcionalidade foi alterada — a atualização é transparente para o uso diário."
        ),
        "severity": "warning",
        "action_url": None,
    },
    {
        "title": "Agenda e controladoria: ajustes do feedback",
        "message": (
            "Corrigimos a sincronização da agenda — compromissos que às vezes "
            "não apareciam voltam a ser listados normalmente. E na controladoria "
            "as datas ficaram mais curtas (dia/mês/ano com 2 dígitos, ex.: 15/06/26) "
            "para caber melhor na tela."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Agenda: edição no modo 'Dia' preserva local e status de perícia",
        "message": (
            "Ao editar um compromisso pela visualização de dia (timeline horária), "
            "o campo Local e o Status da Perícia agora são mantidos corretamente. "
            "Antes, esses campos eram perdidos ao salvar pela timeline."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Alertas: ordem de prioridade corrigida",
        "message": (
            "Os alertas agora aparecem na ordem certa: os mais urgentes (prioridade alta) "
            "primeiro, e os mais recentes antes dos antigos quando a prioridade é igual. "
            "Antes, a ordenação estava invertida por um erro interno."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Correções internas — estabilidade e segurança (10/06)",
        "message": (
            "Aplicamos mais de 20 correções internas nesta versão: "
            "dados de documentos e processos duplicados nos alertas foram eliminados, "
            "erros na agenda com parâmetros de data inválidos foram tratados, "
            "a produtividade na controladoria passou a contar corretamente prazos por responsável, "
            "e diversas rotas internas ganharam proteção extra contra dados malformados."
        ),
        "severity": "warning",
        "action_url": None,
    },
    {
        "title": "Atualize sua foto de perfil",
        "message": (
            "Durante uma migração de servidor, as fotos de perfil foram perdidas e "
            "agora aparecem como uma inicial colorida. Para ter sua foto de volta, "
            "acesse Configurações → Perfil e envie a foto novamente — leva alguns segundos. "
            "Pedimos desculpas pelo transtorno."
        ),
        "severity": "warning",
        "action_url": None,
    },
    {
        "title": "Upload de foto de perfil corrigido — 11/06/2026",
        "message": (
            "O erro que impedia o envio de nova foto de perfil foi corrigido. "
            "Se você tentou atualizar sua foto e recebeu uma mensagem de erro, "
            "tente novamente agora — deve funcionar normalmente."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Agenda: seleção de responsáveis sem Ctrl/Cmd",
        "message": (
            "A escolha de responsáveis no compromisso ficou mais simples: agora há "
            "uma caixinha discreta para marcar uma ou várias pessoas. Não precisa "
            "segurar Ctrl ou Cmd para selecionar mais de um nome."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Controladoria: colunas ajustáveis e tabela mais compacta",
        "message": (
            "A tabela de prazos ficou mais compacta nos pontos que desperdiçavam "
            "espaço. Também dá para arrastar a divisória do cabeçalho para aumentar "
            "ou diminuir a largura das colunas, como uma janela do Windows. O ajuste "
            "fica salvo neste navegador."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "WhatsApp: conexão mais estável",
        "message": (
            "A conexão do WhatsApp foi ajustada para evitar estados confusos. Quando "
            "for preciso reconectar, o CaseHub mostra o QR corretamente; quando a "
            "sessão estiver encerrada de propósito, ela não tenta voltar sozinha."
        ),
        "severity": "info",
        "action_url": None,
    },
    {
        "title": "Chat da equipe: abas mais limpas e sem piscar",
        "message": (
            "As abas de conversa do chat da equipe foram corrigidas: elas não piscam "
            "mais durante o uso, a foto agora aparece à esquerda do nome em uma única "
            "linha mais compacta, e o Maestro ganhou seu próprio avatar. "
            "Ficou mais leve e fácil de ler."
        ),
        "severity": "info",
        "action_url": None,
    },
]


def _existing_patch_note(db, user_id: int, title: str):
    """Retorna a hotfix existente deste usuário para este título, se houver."""
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.notification_type == "hotfix",
            Notification.title == title,
        )
        .first()
    )


def seed_patch_notes(org_id: int = None, org_slug: str = None) -> None:
    """Cria as patch notes como hotfix para cada usuário das orgs-alvo.

    Sem filtro -> todas as organizações. Idempotente por (user_id, title).
    """
    init_db()
    db = next(get_db())

    try:
        org_query = db.query(Organization)
        if org_id is not None:
            org_query = org_query.filter(Organization.id == org_id)
        elif org_slug is not None:
            org_query = org_query.filter(Organization.slug == org_slug)

        orgs = org_query.all()
        if not orgs:
            print("[seed_patch_notes] Nenhuma organização encontrada. Nada a fazer.")
            return

        total_created = 0
        total_updated = 0
        total_skipped = 0

        for org in orgs:
            users = db.query(User).filter(User.org_id == org.id).all()
            if not users:
                print(f"[seed_patch_notes] Org '{org.slug}' (id={org.id}) sem usuários. Pulando.")
                continue

            org_created = 0
            org_updated = 0
            for user in users:
                for note in PATCH_NOTES:
                    existing = _existing_patch_note(db, user.id, note["title"])
                    if existing:
                        changed = False
                        next_message = note["message"]
                        next_severity = note.get("severity", "info")
                        next_action_url = note.get("action_url")

                        if existing.message != next_message:
                            existing.message = next_message
                            changed = True
                        if existing.severity != next_severity:
                            existing.severity = next_severity
                            changed = True
                        if existing.action_url != next_action_url:
                            existing.action_url = next_action_url
                            changed = True

                        if changed:
                            existing.is_read = False
                            existing.read_at = None
                            org_updated += 1
                            total_updated += 1
                        else:
                            total_skipped += 1
                        continue

                    db.add(
                        Notification(
                            org_id=org.id,
                            user_id=user.id,
                            notification_type="hotfix",
                            title=note["title"],
                            message=note["message"],
                            severity=note.get("severity", "info"),
                            action_url=note.get("action_url"),
                            is_read=False,
                        )
                    )
                    org_created += 1
                    total_created += 1

            db.flush()
            print(
                f"[seed_patch_notes] Org '{org.slug}' (id={org.id}): "
                f"{len(users)} usuário(s), {org_created} nota(s) criada(s), "
                f"{org_updated} atualizada(s)."
            )

        db.commit()
        print(
            f"\n[seed_patch_notes] Concluído. "
            f"Criadas: {total_created} | Atualizadas: {total_updated} | "
            f"Já existentes (puladas): {total_skipped}."
        )

    except Exception as e:
        db.rollback()
        print(f"[seed_patch_notes] ERRO: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed idempotente das patch notes (hotfix) por usuário da org."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--org-id", type=int, default=None, help="Limita a uma org por id.")
    group.add_argument("--org-slug", type=str, default=None, help="Limita a uma org por slug.")
    args = parser.parse_args()

    seed_patch_notes(org_id=args.org_id, org_slug=args.org_slug)
