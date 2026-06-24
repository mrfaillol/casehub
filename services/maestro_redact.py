"""PII redaction p/ o contexto do Maestro enviado a providers EXTERNOS.

So quando provider externo (NVIDIA NIM etc.) ativo. Ollama local fica integro.
Pseudonimiza nomes de cliente/caso/tarefa + regex CNJ/CPF/CNPJ/email/telefone/OAB.
Retorna (texto, unmap) p/ un-redaction da resposta (NVIDIA nunca ve o real; o
usuario ve). Rulings 2026-06-18 activate/order-nvidia-maestro. Fail-closed.
"""
import re
from sqlalchemy import text as _sql_text

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_CNJ = re.compile(r"\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b")
_OAB = re.compile(r"\bOAB[\s/.\-]*[A-Z]{2}[\s.\-]*\d{3,6}\b", re.IGNORECASE)


def _entities(db, org_id):
    names = set()
    try:
        for r in db.execute(_sql_text(
            "SELECT first_name, last_name FROM clients WHERE org_id = :oid"
        ), {"oid": org_id}):
            full = ((r[0] or "") + " " + (r[1] or "")).strip()
            if full:
                names.add(full)
            for part in (r[0], r[1]):
                p = (part or "").strip()
                if len(p) >= 3:
                    names.add(p)
    except Exception:
        pass
    phrases = set()  # nomes de caso e titulos de tarefa (texto livre) -> string inteira
    for q in (
        "SELECT case_name FROM cases WHERE org_id = :oid AND case_name IS NOT NULL",
        "SELECT title FROM tasks WHERE org_id = :oid AND title IS NOT NULL",
    ):
        try:
            for r in db.execute(_sql_text(q), {"oid": org_id}):
                v = (r[0] or "").strip()
                if len(v) >= 4:
                    phrases.add(v)
        except Exception:
            pass
    return names, phrases


def redact_firm_context(context, db, org_id):
    """Retorna (texto_redigido, unmap={pseudonimo: original})."""
    if not context:
        return context, {}
    text = context
    unmap = {}
    names, phrases = _entities(db, org_id)
    for i, ph in enumerate(sorted(phrases, key=len, reverse=True)):
        if ph in text:
            ps = "Caso_{}".format(i + 1)
            text = text.replace(ph, ps)
            unmap[ps] = ph
    seen = {}
    for n in sorted(names, key=len, reverse=True):
        if n and n in text:
            if n not in seen:
                seen[n] = "Cliente_{}".format(len(seen) + 1)
            ps = seen[n]
            text = text.replace(n, ps)
            unmap[ps] = n
    text = _CNJ.sub("[PROCESSO]", text)
    text = _CNPJ.sub("[CNPJ]", text)
    text = _CPF.sub("[CPF]", text)
    text = _OAB.sub("[OAB]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = _PHONE.sub("[TELEFONE]", text)
    return text, unmap


def unredact(text, unmap):
    """Reverte pseudonimos -> original na resposta. NVIDIA nunca viu o original."""
    if not text or not unmap:
        return text
    for ps in sorted(unmap, key=len, reverse=True):
        text = text.replace(ps, unmap[ps])
    return text
