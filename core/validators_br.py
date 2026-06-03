"""
CaseHub - Brazilian Document Validators
CPF, CNPJ, OAB, and processo number (CNJ format) validation.
"""
import re


def validate_cpf(cpf: str) -> bool:
    """Validate a Brazilian CPF number."""
    cpf = re.sub(r"[^\d]", "", cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        val = sum(int(cpf[j]) * ((i + 1) - j) for j in range(i))
        digit = (val * 10 % 11) % 10
        if int(cpf[i]) != digit:
            return False
    return True


def validate_cnpj(cnpj: str) -> bool:
    """Validate a Brazilian CNPJ number."""
    cnpj = re.sub(r"[^\d]", "", cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for i, weights in [(12, weights1), (13, weights2)]:
        val = sum(int(cnpj[j]) * weights[j] for j in range(i))
        digit = 11 - (val % 11)
        if digit >= 10:
            digit = 0
        if int(cnpj[i]) != digit:
            return False
    return True


def format_cpf(cpf: str) -> str:
    """Format CPF: 000.000.000-00"""
    cpf = re.sub(r"[^\d]", "", cpf)
    if len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def format_cnpj(cnpj: str) -> str:
    """Format CNPJ: 00.000.000/0000-00"""
    cnpj = re.sub(r"[^\d]", "", cnpj)
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def format_oab(oab: str) -> str:
    """Format OAB number: OAB/UF 123.456"""
    oab = oab.strip().upper()
    if not oab:
        return ""
    match = re.match(r"(?:OAB/?)?(\w{2})\s*(\d+)", oab)
    if match:
        uf = match.group(1)
        num = match.group(2)
        if len(num) > 3:
            num = f"{num[:-3]}.{num[-3:]}"
        return f"OAB/{uf} {num}"
    return oab


def validate_processo_cnj(numero: str) -> bool:
    """Validate processo number in CNJ format: NNNNNNN-DD.AAAA.J.TR.OOOO"""
    pattern = r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
    return bool(re.match(pattern, numero))


def format_processo_cnj(numero: str) -> str:
    """Format processo number to CNJ format."""
    digits = re.sub(r"[^\d]", "", numero)
    if len(digits) != 20:
        return numero
    return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"


# Brazilian tribunais for dropdown
TRIBUNAIS = [
    ("TJAC", "Tribunal de Justiça do Acre"),
    ("TJAL", "Tribunal de Justiça de Alagoas"),
    ("TJAM", "Tribunal de Justiça do Amazonas"),
    ("TJAP", "Tribunal de Justiça do Amapá"),
    ("TJBA", "Tribunal de Justiça da Bahia"),
    ("TJCE", "Tribunal de Justiça do Ceará"),
    ("TJDFT", "Tribunal de Justiça do DF"),
    ("TJES", "Tribunal de Justiça do Espírito Santo"),
    ("TJGO", "Tribunal de Justiça de Goiás"),
    ("TJMA", "Tribunal de Justiça do Maranhão"),
    ("TJMG", "Tribunal de Justiça de Minas Gerais"),
    ("TJMS", "Tribunal de Justiça do Mato Grosso do Sul"),
    ("TJMT", "Tribunal de Justiça do Mato Grosso"),
    ("TJPA", "Tribunal de Justiça do Pará"),
    ("TJPB", "Tribunal de Justiça da Paraíba"),
    ("TJPE", "Tribunal de Justiça de Pernambuco"),
    ("TJPI", "Tribunal de Justiça do Piauí"),
    ("TJPR", "Tribunal de Justiça do Paraná"),
    ("TJRJ", "Tribunal de Justiça do Rio de Janeiro"),
    ("TJRN", "Tribunal de Justiça do Rio Grande do Norte"),
    ("TJRO", "Tribunal de Justiça de Rondônia"),
    ("TJRR", "Tribunal de Justiça de Roraima"),
    ("TJRS", "Tribunal de Justiça do Rio Grande do Sul"),
    ("TJSC", "Tribunal de Justiça de Santa Catarina"),
    ("TJSE", "Tribunal de Justiça de Sergipe"),
    ("TJSP", "Tribunal de Justiça de São Paulo"),
    ("TJTO", "Tribunal de Justiça do Tocantins"),
    ("TRF1", "Tribunal Regional Federal da 1ª Região"),
    ("TRF2", "Tribunal Regional Federal da 2ª Região"),
    ("TRF3", "Tribunal Regional Federal da 3ª Região"),
    ("TRF4", "Tribunal Regional Federal da 4ª Região"),
    ("TRF5", "Tribunal Regional Federal da 5ª Região"),
    ("TRF6", "Tribunal Regional Federal da 6ª Região"),
    ("TRT1", "Tribunal Regional do Trabalho da 1ª Região"),
    ("TRT2", "Tribunal Regional do Trabalho da 2ª Região"),
    ("TRT3", "Tribunal Regional do Trabalho da 3ª Região"),
    ("TRT4", "Tribunal Regional do Trabalho da 4ª Região"),
    ("TRT15", "Tribunal Regional do Trabalho da 15ª Região"),
    ("TST", "Tribunal Superior do Trabalho"),
    ("STJ", "Superior Tribunal de Justiça"),
    ("STF", "Supremo Tribunal Federal"),
]

# Brazilian document types for classification
TIPOS_DOCUMENTO = [
    "peticao_inicial",
    "contestacao",
    "replica",
    "recurso_apelacao",
    "recurso_especial",
    "recurso_extraordinario",
    "agravo_instrumento",
    "agravo_interno",
    "embargos_declaracao",
    "mandado_seguranca",
    "habeas_corpus",
    "procuracao",
    "substabelecimento",
    "contrato",
    "parecer",
    "certidao",
    "oficio",
    "mandado",
    "despacho",
    "sentenca",
    "acordao",
    "ata_audiencia",
    "laudo_pericial",
    "comprovante_pagamento",
    "guia_custas",
    "documento_pessoal",
    "outro",
]

# Tipos de ação comuns
TIPOS_ACAO = [
    ("acao_indenizatoria", "Ação Indenizatória"),
    ("acao_cobranca", "Ação de Cobrança"),
    ("acao_trabalhista", "Reclamação Trabalhista"),
    ("execucao_titulo", "Execução de Título"),
    ("execucao_fiscal", "Execução Fiscal"),
    ("mandado_seguranca", "Mandado de Segurança"),
    ("habeas_corpus", "Habeas Corpus"),
    ("acao_civil_publica", "Ação Civil Pública"),
    ("acao_popular", "Ação Popular"),
    ("acao_possessoria", "Ação Possessória"),
    ("acao_despejo", "Ação de Despejo"),
    ("acao_consignacao", "Ação de Consignação"),
    ("acao_revisional", "Ação Revisional"),
    ("acao_declaratoria", "Ação Declaratória"),
    ("acao_monitoria", "Ação Monitória"),
    ("divorcio", "Divórcio"),
    ("inventario", "Inventário"),
    ("interdição", "Interdição"),
    ("tutela_curatela", "Tutela/Curatela"),
    ("usucapiao", "Usucapião"),
    ("retificacao", "Retificação de Registro"),
    ("outro", "Outro"),
]

# Fases processuais
FASES_PROCESSUAIS = [
    ("distribuicao", "Distribuição"),
    ("citacao", "Citação"),
    ("conhecimento", "Conhecimento"),
    ("instrucao", "Instrução"),
    ("audiencia", "Audiência"),
    ("julgamento", "Julgamento"),
    ("recursal", "Fase Recursal"),
    ("transito_julgado", "Trânsito em Julgado"),
    ("execucao", "Execução"),
    ("cumprimento_sentenca", "Cumprimento de Sentença"),
    ("liquidacao", "Liquidação"),
    ("arquivado", "Arquivado"),
    ("suspenso", "Suspenso"),
]
