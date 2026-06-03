"""
CaseHub i18n module - Internationalization support

This package provides backward-compatible short keys.
The full expanded translation system lives in the root-level i18n.py file.
"""

DEFAULT_LANG = "en"

# Short keys kept here for backward compatibility with code that does:
#   from i18n import get_translations
# The full dot-notation translation system is in /i18n.py (root level).

TRANSLATIONS = {
    "en": {
        "dashboard": "Dashboard",
        "clients": "Clients",
        "cases": "Cases",
        "documents": "Documents",
        "leads": "Leads",
        "settings": "Settings",
        "logout": "Logout",
        "search": "Search",
        "save": "Save",
        "cancel": "Cancel",
        "delete": "Delete",
        "edit": "Edit",
        "add": "Add",
        "upload": "Upload",
        "download": "Download",
        "status": "Status",
        "actions": "Actions",
        "google_calendar_default_title": "Appointment",
        "google_calendar_created_by": "Created by CaseHub.",
        "google_calendar_client_label": "Client",
        "google_calendar_type_label": "Type",
        "google_calendar_neutral_title": "CaseHub appointment",
        "google_calendar_neutral_description": "Created by CaseHub. Open CaseHub for details.",
        "google_calendar_notice_neutral": "Neutral mode active: Google Calendar receives only the time and private ID; title, client, type, and notes stay in CaseHub.",
        "google_calendar_notice_details": "Upon connecting, Google Calendar will receive the title, client, type, and notes of synced appointments. Use only Google accounts controlled by the office/tenant.",
        "name": "Name",
        "email": "Email",
        "phone": "Phone",
        "date": "Date",
        "type": "Type",
        "notes": "Notes",
        "welcome": "Welcome",
        "loading": "Loading...",
        "error.internal": "Internal Error",
        "error.internal_detail": "Something went wrong on our end. Please try again later.",
        "error.reference": "Error reference",
        "error.try_again": "Try again",
        "error.go_dashboard": "Go to Dashboard",
        "error.contact_support": "If the problem persists, contact support:",
        "error.plan_unavailable": "Resource unavailable on this plan",
        "error.plan_unavailable_detail": "This resource is not included in the current plan. You can keep using CaseHub or review the plan.",
    },
    "pt": {
        "dashboard": "Painel",
        "clients": "Clientes",
        "cases": "Casos",
        "documents": "Documentos",
        "leads": "Leads",
        "settings": "Configuracoes",
        "logout": "Sair",
        "search": "Buscar",
        "save": "Salvar",
        "cancel": "Cancelar",
        "delete": "Excluir",
        "edit": "Editar",
        "add": "Adicionar",
        "upload": "Enviar",
        "download": "Baixar",
        "status": "Status",
        "actions": "Acoes",
        "google_calendar_default_title": "Agendamento",
        "google_calendar_created_by": "Criado pelo CaseHub.",
        "google_calendar_client_label": "Cliente",
        "google_calendar_type_label": "Tipo",
        "google_calendar_neutral_title": "Compromisso CaseHub",
        "google_calendar_neutral_description": "Criado pelo CaseHub. Abra o CaseHub para detalhes.",
        "google_calendar_notice_neutral": "Modo neutro ativo: o Google Calendar recebe horário e identificador privado do compromisso; título, cliente, tipo e notas ficam apenas no CaseHub.",
        "google_calendar_notice_details": "Ao conectar, o Google Calendar receberá título, cliente, tipo e notas dos compromissos sincronizados. Use apenas conta Google controlada pelo escritório/tenant.",
        "name": "Nome",
        "email": "Email",
        "phone": "Telefone",
        "date": "Data",
        "type": "Tipo",
        "notes": "Notas",
        "welcome": "Bem-vindo",
        "loading": "Carregando...",
        "error.internal": "Erro Interno",
        "error.internal_detail": "Algo deu errado do nosso lado. Por favor, tente novamente mais tarde.",
        "error.reference": "Referencia do erro",
        "error.try_again": "Tentar novamente",
        "error.go_dashboard": "Ir para o Painel",
        "error.contact_support": "Se o problema persistir, entre em contato:",
        "error.plan_unavailable": "Recurso indisponivel no plano",
        "error.plan_unavailable_detail": "Este recurso nao esta incluso no plano atual. Voce pode continuar usando o CaseHub ou revisar o plano.",
    },
}


def get_translations(lang: str = None) -> dict:
    """Get translations for a specific language."""
    if lang is None:
        lang = DEFAULT_LANG
    # Map pt-BR to pt for this module's short keys
    if lang == "pt-BR":
        lang = "pt"
    return TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
