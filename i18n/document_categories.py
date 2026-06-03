"""
CaseHub - Document Category Translations (i18n)

Provides translations for document categories in multiple languages.
Primary language: English (canonical, stored in database)
Secondary: Portuguese (for Brazilian staff/clients)

Usage:
    from i18n.document_categories import get_category_label, get_all_categories

    # Get translated label
    label = get_category_label("Letter of Recommendation", lang="pt")
    # Returns: "Carta de Recomendação"

    # Get all categories with translations
    categories = get_all_categories(lang="en")

Created: 2026-03-03
Purpose: Client Portal internationalization for document categories
"""

from typing import Dict, List, Optional


# Canonical document categories (English) with Portuguese translations
# English is the canonical form stored in the database
DOCUMENT_CATEGORIES: Dict[str, Dict[str, str]] = {
    # Personal Documents
    "Passport": {
        "en": "Passport",
        "pt": "Passaporte",
    },
    "I-94 Travel Record": {
        "en": "I-94 Travel Record",
        "pt": "Registro de Viagem I-94",
    },
    "Visa": {
        "en": "Visa",
        "pt": "Visto",
    },
    "EAD Card": {
        "en": "EAD Card",
        "pt": "Cartão EAD",
    },
    "Green Card": {
        "en": "Green Card",
        "pt": "Green Card",
    },
    "Birth Certificate": {
        "en": "Birth Certificate",
        "pt": "Certidão de Nascimento",
    },
    "Marriage Certificate": {
        "en": "Marriage Certificate",
        "pt": "Certidão de Casamento",
    },
    "Photo": {
        "en": "Photo",
        "pt": "Foto",
    },

    # Educational Documents
    "Diploma": {
        "en": "Diploma",
        "pt": "Diploma",
    },
    "Academic Transcript": {
        "en": "Academic Transcript",
        "pt": "Histórico Escolar",
    },
    "Credential Evaluation": {
        "en": "Credential Evaluation",
        "pt": "Avaliação de Credenciais",
    },

    # Professional Documents
    "Resume/CV": {
        "en": "Resume/CV",
        "pt": "Currículo",
    },
    "Letter of Recommendation": {
        "en": "Letter of Recommendation",
        "pt": "Carta de Recomendação",
    },
    "Employment Letter": {
        "en": "Employment Letter",
        "pt": "Carta de Emprego",
    },
    "Employment Contract": {
        "en": "Employment Contract",
        "pt": "Contrato de Trabalho",
    },
    "Award/Recognition": {
        "en": "Award/Recognition",
        "pt": "Prêmio/Reconhecimento",
    },
    "Professional Membership": {
        "en": "Professional Membership",
        "pt": "Associação Profissional",
    },
    "Publication": {
        "en": "Publication",
        "pt": "Publicação",
    },
    "Portfolio/Work Samples": {
        "en": "Portfolio/Work Samples",
        "pt": "Portfólio/Amostras de Trabalho",
    },

    # Financial Documents
    "Tax Return": {
        "en": "Tax Return",
        "pt": "Declaração de Imposto de Renda",
    },
    "Financial Statement": {
        "en": "Financial Statement",
        "pt": "Extrato Financeiro",
    },
    "Pay Stub": {
        "en": "Pay Stub",
        "pt": "Holerite/Contracheque",
    },

    # Immigration Documents
    "USCIS Form": {
        "en": "USCIS Form",
        "pt": "Formulário USCIS",
    },
    "Receipt Notice": {
        "en": "Receipt Notice",
        "pt": "Aviso de Recebimento",
    },
    "Approval Notice": {
        "en": "Approval Notice",
        "pt": "Aviso de Aprovação",
    },
    "Request for Evidence": {
        "en": "Request for Evidence",
        "pt": "Solicitação de Evidência (RFE)",
    },
    "Supporting Evidence": {
        "en": "Supporting Evidence",
        "pt": "Evidência de Suporte",
    },
    "Personal Statement": {
        "en": "Personal Statement",
        "pt": "Declaração Pessoal",
    },

    # Additional Documents
    "Medical Records": {
        "en": "Medical Records",
        "pt": "Registros Médicos",
    },
    "Police Certificate": {
        "en": "Police Certificate",
        "pt": "Certidão de Antecedentes",
    },
    "Cover Letter": {
        "en": "Cover Letter",
        "pt": "Carta de Apresentação",
    },
    "Affidavit": {
        "en": "Affidavit",
        "pt": "Declaração Juramentada",
    },

    # Internal (hidden from clients by default)
    "Case Admin": {
        "en": "Case Admin",
        "pt": "Admin do Caso",
        "internal": True,
    },
    "Checklist": {
        "en": "Checklist",
        "pt": "Checklist",
        "internal": True,
    },
    "Retainer": {
        "en": "Retainer Agreement",
        "pt": "Contrato de Honorários",
        "internal": True,
    },
    "Brief": {
        "en": "Legal Brief",
        "pt": "Petição",
        "internal": True,
    },
    "Exhibit": {
        "en": "Exhibit",
        "pt": "Anexo/Exhibit",
        "internal": True,
    },
    "Questionnaire": {
        "en": "Questionnaire",
        "pt": "Questionário",
        "internal": True,
    },

    # Fallback
    "Other Document": {
        "en": "Other Document",
        "pt": "Outro Documento",
    },
}

# Document category groups for UI display
CATEGORY_GROUPS = {
    "en": {
        "Personal Documents": [
            "Passport", "I-94 Travel Record", "Visa", "EAD Card",
            "Green Card", "Birth Certificate", "Marriage Certificate", "Photo"
        ],
        "Educational": [
            "Diploma", "Academic Transcript", "Credential Evaluation"
        ],
        "Professional": [
            "Resume/CV", "Letter of Recommendation", "Employment Letter",
            "Employment Contract", "Award/Recognition", "Professional Membership",
            "Publication", "Portfolio/Work Samples"
        ],
        "Financial": [
            "Tax Return", "Financial Statement", "Pay Stub"
        ],
        "Immigration": [
            "USCIS Form", "Receipt Notice", "Approval Notice",
            "Request for Evidence", "Supporting Evidence", "Personal Statement"
        ],
        "Other": [
            "Medical Records", "Police Certificate", "Cover Letter",
            "Affidavit", "Other Document"
        ],
    },
    "pt": {
        "Documentos Pessoais": [
            "Passport", "I-94 Travel Record", "Visa", "EAD Card",
            "Green Card", "Birth Certificate", "Marriage Certificate", "Photo"
        ],
        "Educacional": [
            "Diploma", "Academic Transcript", "Credential Evaluation"
        ],
        "Profissional": [
            "Resume/CV", "Letter of Recommendation", "Employment Letter",
            "Employment Contract", "Award/Recognition", "Professional Membership",
            "Publication", "Portfolio/Work Samples"
        ],
        "Financeiro": [
            "Tax Return", "Financial Statement", "Pay Stub"
        ],
        "Imigração": [
            "USCIS Form", "Receipt Notice", "Approval Notice",
            "Request for Evidence", "Supporting Evidence", "Personal Statement"
        ],
        "Outros": [
            "Medical Records", "Police Certificate", "Cover Letter",
            "Affidavit", "Other Document"
        ],
    },
}


def get_category_label(category: str, lang: str = "en") -> str:
    """Get the translated label for a document category."""
    cat_info = DOCUMENT_CATEGORIES.get(category)
    if cat_info:
        return cat_info.get(lang, cat_info.get("en", category))
    return category


def get_all_categories(lang: str = "en", include_internal: bool = False) -> List[Dict[str, str]]:
    """Get all document categories with labels."""
    result = []
    for key, info in DOCUMENT_CATEGORIES.items():
        if not include_internal and info.get("internal"):
            continue
        result.append({
            "value": key,
            "label": info.get(lang, info.get("en", key)),
            "internal": info.get("internal", False),
        })
    return result


def get_category_groups(lang: str = "en") -> Dict[str, List[Dict[str, str]]]:
    """Get categories organized by group with translated labels."""
    groups = CATEGORY_GROUPS.get(lang, CATEGORY_GROUPS["en"])
    result = {}
    for group_name, categories in groups.items():
        result[group_name] = [
            {
                "value": cat,
                "label": get_category_label(cat, lang),
            }
            for cat in categories
        ]
    return result


def is_internal_category(category: str) -> bool:
    """Check if a category is internal (should be hidden from clients)."""
    cat_info = DOCUMENT_CATEGORIES.get(category, {})
    return cat_info.get("internal", False)


def get_client_visible_categories(lang: str = "en") -> List[Dict[str, str]]:
    """Get only categories that should be visible to clients."""
    return get_all_categories(lang=lang, include_internal=False)
