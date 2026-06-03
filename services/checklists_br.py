"""
CaseHub — Brazilian Document Checklists by Case Type
Auto-generates required documents when a new case is created.

Maps tipo_acao values from the case form to their required document checklists.
"""

CHECKLISTS = {
    "civel": {
        "nome": "Checklist Cível",
        "documentos": [
            {"nome": "Procuração Ad Judicia", "obrigatorio": True},
            {"nome": "Documentos pessoais (RG/CPF)", "obrigatorio": True},
            {"nome": "Comprovante de residência", "obrigatorio": True},
            {"nome": "Declaração de hipossuficiência", "obrigatorio": False},
            {"nome": "Provas documentais", "obrigatorio": True},
            {"nome": "Comprovante de tentativa de conciliação", "obrigatorio": False},
        ]
    },
    "trabalhista": {
        "nome": "Checklist Trabalhista",
        "documentos": [
            {"nome": "Procuração Ad Judicia", "obrigatorio": True},
            {"nome": "CTPS (carteira de trabalho)", "obrigatorio": True},
            {"nome": "Holerites/contracheques", "obrigatorio": True},
            {"nome": "Termo de rescisão (TRCT)", "obrigatorio": True},
            {"nome": "Extrato do FGTS", "obrigatorio": True},
            {"nome": "Guias de seguro-desemprego", "obrigatorio": False},
            {"nome": "Comprovante de ponto/jornada", "obrigatorio": False},
            {"nome": "Contrato de trabalho", "obrigatorio": True},
            {"nome": "Atestados médicos", "obrigatorio": False},
        ]
    },
    "previdenciario": {
        "nome": "Checklist Previdenciário",
        "documentos": [
            {"nome": "Procuração Ad Judicia", "obrigatorio": True},
            {"nome": "CNIS (extrato previdenciário)", "obrigatorio": True},
            {"nome": "Documentos pessoais", "obrigatorio": True},
            {"nome": "Carta de indeferimento INSS", "obrigatorio": True},
            {"nome": "Laudos médicos", "obrigatorio": False},
            {"nome": "PPP (Perfil Profissiográfico)", "obrigatorio": False},
            {"nome": "CTPS com registros", "obrigatorio": True},
            {"nome": "Comprovantes de contribuição", "obrigatorio": False},
        ]
    },
    "criminal": {
        "nome": "Checklist Criminal",
        "documentos": [
            {"nome": "Procuração Ad Judicia", "obrigatorio": True},
            {"nome": "Boletim de ocorrência", "obrigatorio": True},
            {"nome": "Folha de antecedentes", "obrigatorio": True},
            {"nome": "Documentos pessoais", "obrigatorio": True},
            {"nome": "Comprovante de residência", "obrigatorio": True},
            {"nome": "Comprovante de ocupação lícita", "obrigatorio": False},
        ]
    },
    "tributario": {
        "nome": "Checklist Tributário",
        "documentos": [
            {"nome": "Procuração Ad Judicia", "obrigatorio": True},
            {"nome": "Contrato social/estatuto", "obrigatorio": True},
            {"nome": "CNPJ", "obrigatorio": True},
            {"nome": "Guias de recolhimento", "obrigatorio": True},
            {"nome": "Notas fiscais", "obrigatorio": False},
            {"nome": "Declarações fiscais (IRPJ/CSLL)", "obrigatorio": True},
            {"nome": "Auto de infração", "obrigatorio": False},
        ]
    },
    "familia": {
        "nome": "Checklist Família",
        "documentos": [
            {"nome": "Procuração Ad Judicia", "obrigatorio": True},
            {"nome": "Certidão de casamento", "obrigatorio": True},
            {"nome": "Certidão de nascimento dos filhos", "obrigatorio": False},
            {"nome": "Declaração de bens", "obrigatorio": True},
            {"nome": "Comprovantes de renda", "obrigatorio": True},
            {"nome": "Documentos pessoais", "obrigatorio": True},
            {"nome": "Acordo extrajudicial (se houver)", "obrigatorio": False},
        ]
    },
}

# Maps form tipo_acao values to checklist keys
TIPO_ACAO_MAP = {
    "acao_indenizatoria": "civel",
    "acao_trabalhista": "trabalhista",
    "execucao_fiscal": "tributario",
    "mandado_seguranca": "civel",
    "habeas_corpus": "criminal",
    "recurso_especial": "civel",
    "acao_civil_publica": "civel",
    "divorcio": "familia",
    "inventario": "familia",
}


def get_checklist(tipo_acao: str) -> dict:
    """Get checklist for a specific case type.

    Accepts either a checklist key (e.g. 'civel', 'trabalhista') or a
    form tipo_acao value (e.g. 'acao_trabalhista', 'divorcio').
    Returns the matching checklist dict, or the cível checklist as default.
    """
    if not tipo_acao:
        return CHECKLISTS["civel"]

    tipo = tipo_acao.lower().strip()

    # Direct match
    if tipo in CHECKLISTS:
        return CHECKLISTS[tipo]

    # Map from form value
    if tipo in TIPO_ACAO_MAP:
        return CHECKLISTS[TIPO_ACAO_MAP[tipo]]

    # Fuzzy substring match
    for key in CHECKLISTS:
        if key in tipo:
            return CHECKLISTS[key]

    return CHECKLISTS["civel"]


def list_available_types() -> list[str]:
    """Return all available checklist type keys."""
    return list(CHECKLISTS.keys())
