"""Official legal RAG for Maestro.

The core contract is deliberately strict:

- only verified official/public sources are eligible;
- every answerable legal context block carries URL + SHA citation metadata;
- no remote model/provider call is made here;
- retrieval degrades to empty context, letting Maestro refuse instead of guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
import os
import re
import unicodedata
from typing import Iterable, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import MaestroLegalChunk, MaestroLegalDocument, MaestroLegalSource
from services.maestro_repo_index import redact_secret_lines

logger = logging.getLogger(__name__)

PARSER_VERSION = "maestro-legal-v1"
MAX_SOURCE_TEXT_CHARS = 2_000_000
MAX_CONTEXT_CHARS_PER_CHUNK = 1400
DEFAULT_TOP_K = 5

LEGAL_TERMS_RE = re.compile(
    r"(?ix)\b("
    r"art(?:igo)?\.?\s*\d+|s[uú]mula\s*\d+|lei\s*\d+|"
    r"constitui[cç][aã]o|c[oó]digo\s+(?:civil|penal|tribut[aá]rio|processo|consumidor|trabalho)|"
    r"cpc|clt|cdc|ctn|lgpd|jurisprud[eê]ncia|ac[oó]rd[aã]o|ementa|precedente|"
    r"stf|stj|tst|trf|tj|trt|datajud|pdpj|domic[ií]lio\s+judicial"
    r")\b"
)

STOPWORDS = {
    "sobre", "para", "com", "sem", "dos", "das", "que", "qual", "quais",
    "como", "onde", "isso", "este", "esta", "esse", "essa", "diz", "fale",
    "explique", "me", "de", "do", "da", "em", "um", "uma", "os", "as",
    "no", "na", "nos", "nas", "por", "pra", "ao", "aos", "e", "ou",
}

SOURCE_ALIAS_RULES = {
    "cpc": ("cpc", "processo civil", "lei 13.105", "l13105"),
    "clt": ("clt", "trabalho", "del5452"),
    "cdc": ("cdc", "consumidor", "l8078"),
    "lgpd": ("lgpd", "protecao de dados", "l13709"),
    "datajud": ("datajud",),
    "pdpj": ("pdpj", "domicilio judicial"),
    "cf": ("constituicao", "constitucional", "constituicaocompilado"),
}


@dataclass(frozen=True)
class LegalCitation:
    source_id: int
    document_id: int
    chunk_id: int
    authority: str
    title: str
    url: str
    citation_label: str
    content_sha256: str

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "authority": self.authority,
            "title": self.title,
            "url": self.url,
            "citation_label": self.citation_label,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class LegalRetrievalResult:
    looks_legal: bool
    context: Optional[str]
    citations: List[LegalCitation]

    @property
    def has_context(self) -> bool:
        return bool(self.context and self.citations)


def legal_rag_enabled() -> bool:
    """Legal retrieval is safe by default: it only reads verified local corpus."""
    raw = os.getenv("CASEHUB_MAESTRO_LEGAL_RAG_ENABLED")
    if raw is None:
        return True
    return raw.lower() in {"1", "true", "yes", "on"}


def legal_source_required() -> bool:
    """Refuse legal claims without official source by default."""
    raw = os.getenv("CASEHUB_MAESTRO_LEGAL_SOURCE_REQUIRED")
    if raw is None:
        return True
    return raw.lower() in {"1", "true", "yes", "on"}


def looks_like_legal_question(message: str) -> bool:
    return bool(LEGAL_TERMS_RE.search(message or ""))


def _sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="replace")).hexdigest()


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.lower()


def _tokens(value: str) -> List[str]:
    normalized = _normalize(value)
    found = re.findall(r"[a-z0-9]{3,}", normalized)
    return [tok for tok in found if tok not in STOPWORDS]


def _article_number_boost(chunk_text: str, query_tokens: List[str]) -> float:
    numeric_tokens = [tok for tok in query_tokens if tok.isdigit()]
    if not numeric_tokens:
        return 0.0
    normalized = _normalize(chunk_text)
    score = 0.0
    for number in numeric_tokens[:3]:
        if re.search(rf"\bart\.?\s*{re.escape(number)}\b", normalized):
            score += 2.0
        elif re.search(rf"\bartigo\s*{re.escape(number)}\b", normalized):
            score += 2.0
    return score


def _source_alias_boost(query_set: set, doc_title: str, source_key: str, source_title: str) -> float:
    haystack = _normalize(" ".join([doc_title or "", source_key or "", source_title or ""]))
    score = 0.0
    for query_alias, source_aliases in SOURCE_ALIAS_RULES.items():
        if query_alias not in query_set:
            continue
        if any(alias in haystack for alias in source_aliases):
            score += 3.0
    return score


def chunk_legal_text(text: str, *, max_chars: int = 1800, overlap: int = 180) -> List[str]:
    """Chunk official text without introducing dependencies."""
    text = redact_secret_lines((text or "").strip())
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    parts = re.split(r"\n\s*\n", text)
    chunks: List[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(buf) + len(part) + 2 <= max_chars:
            buf = f"{buf}\n\n{part}" if buf else part
            continue
        if buf:
            chunks.append(buf)
        if len(part) <= max_chars:
            buf = part
            continue
        start = 0
        step = max(1, max_chars - overlap)
        while start < len(part):
            chunks.append(part[start:start + max_chars])
            start += step
        buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def upsert_official_document(
    db: Session,
    *,
    source_key: str,
    authority: str,
    title: str,
    url: str,
    text: str,
    jurisdiction: str = "BR",
    document_type: str = "norma",
    metadata: Optional[dict] = None,
) -> MaestroLegalDocument:
    """Create/update one official source document and rebuild its chunks.

    The caller is responsible for ensuring the URL/text came from an official
    source. This function records enough provenance to audit that decision.
    """
    if not source_key or not authority or not title or not url:
        raise ValueError("source_key, authority, title and url are required")

    clean_text = redact_secret_lines((text or "")[:MAX_SOURCE_TEXT_CHARS]).strip()
    if len(clean_text) < 40:
        raise ValueError("official source text is too short to index")

    content_hash = _sha256_text(clean_text)
    now = datetime.now(timezone.utc)

    source = (
        db.query(MaestroLegalSource)
        .filter(MaestroLegalSource.source_key == source_key)
        .first()
    )
    if source is None:
        source = MaestroLegalSource(source_key=source_key)
        db.add(source)

    source.authority = authority
    source.title = title
    source.url = url
    source.jurisdiction = jurisdiction
    source.document_type = document_type
    source.official = True
    source.public = True
    source.trust_status = "verified"
    source.parser_version = PARSER_VERSION
    source.content_sha256 = content_hash
    source.fetched_at = now
    source.extra_metadata = metadata or {}
    db.flush()

    doc = (
        db.query(MaestroLegalDocument)
        .filter(MaestroLegalDocument.source_id == source.id)
        .filter(MaestroLegalDocument.url == url)
        .first()
    )
    if doc is None:
        doc = MaestroLegalDocument(source_id=source.id)
        db.add(doc)

    doc.title = title
    doc.url = url
    doc.document_type = document_type
    doc.jurisdiction = jurisdiction
    doc.content_sha256 = content_hash
    doc.raw_text = clean_text
    doc.status = "active"
    doc.parser_version = PARSER_VERSION
    doc.extra_metadata = metadata or {}
    db.flush()

    db.query(MaestroLegalChunk).filter(MaestroLegalChunk.document_id == doc.id).delete()
    chunks = chunk_legal_text(clean_text)
    for idx, chunk in enumerate(chunks):
        heading = _infer_heading(chunk)
        citation_label = f"{authority} — {title}"
        if heading:
            citation_label = f"{citation_label} — {heading[:90]}"
        db.add(MaestroLegalChunk(
            source_id=source.id,
            document_id=doc.id,
            chunk_index=idx,
            heading=heading,
            content=chunk,
            content_sha256=_sha256_text(chunk),
            citation_label=citation_label[:255],
            url=url,
            active=True,
            extra_metadata={"parser_version": PARSER_VERSION},
        ))

    db.commit()
    db.refresh(doc)
    logger.info("maestro_legal_rag: indexed %s chunks for %s", len(chunks), source_key)
    return doc


def _infer_heading(chunk: str) -> str:
    for line in (chunk or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        if re.match(r"(?i)^(art\.?\s*\d+|cap[ií]tulo|t[ií]tulo|livro|se[cç][aã]o)\b", clean):
            return clean[:180]
        return clean[:120]
    return ""


def retrieve_legal_context(
    db: Session,
    message: str,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> LegalRetrievalResult:
    """Return source-grounded official legal context for one user question."""
    looks_legal = looks_like_legal_question(message)
    if not looks_legal or not legal_rag_enabled():
        return LegalRetrievalResult(looks_legal=looks_legal, context=None, citations=[])

    query_tokens = _tokens(message)
    if not query_tokens:
        return LegalRetrievalResult(looks_legal=True, context=None, citations=[])

    clauses = []
    for tok in query_tokens[:8]:
        like = f"%{tok}%"
        clauses.extend([
            MaestroLegalChunk.content.ilike(like),
            MaestroLegalChunk.heading.ilike(like),
            MaestroLegalDocument.title.ilike(like),
            MaestroLegalSource.title.ilike(like),
        ])

    try:
        query = (
            db.query(MaestroLegalChunk, MaestroLegalDocument, MaestroLegalSource)
            .join(MaestroLegalDocument, MaestroLegalChunk.document_id == MaestroLegalDocument.id)
            .join(MaestroLegalSource, MaestroLegalChunk.source_id == MaestroLegalSource.id)
            .filter(MaestroLegalChunk.active.is_(True))
            .filter(MaestroLegalDocument.status == "active")
            .filter(MaestroLegalSource.official.is_(True))
            .filter(MaestroLegalSource.public.is_(True))
            .filter(MaestroLegalSource.trust_status == "verified")
        )
        if clauses:
            query = query.filter(or_(*clauses))
        # Rank after collecting the eligible official corpus. The alpha corpus is
        # intentionally small (norms/docs, not full jurisprudence); applying a
        # low DB limit before ranking can starve later-indexed sources such as
        # CPC when CF chunks happen to match generic tokens first.
        rows = query.limit(5000).all()
    except Exception as exc:  # noqa: BLE001 — legal retrieval must never break chat
        logger.warning("maestro_legal_rag: retrieval failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return LegalRetrievalResult(looks_legal=True, context=None, citations=[])

    hits = _rank_rows(rows, query_tokens)[:top_k]
    if not hits:
        return LegalRetrievalResult(looks_legal=True, context=None, citations=[])

    blocks = []
    citations: List[LegalCitation] = []
    for n, (chunk, doc, source, score) in enumerate(hits, start=1):
        snippet = chunk.content.strip()
        if len(snippet) > MAX_CONTEXT_CHARS_PER_CHUNK:
            snippet = snippet[:MAX_CONTEXT_CHARS_PER_CHUNK] + "..."
        blocks.append(
            f"[Fonte juridica oficial {n}: {chunk.citation_label}] "
            f"(autoridade: {source.authority}; url: {chunk.url}; "
            f"sha256: {chunk.content_sha256}; score: {score:.2f})\n{snippet}"
        )
        citations.append(LegalCitation(
            source_id=int(source.id),
            document_id=int(doc.id),
            chunk_id=int(chunk.id),
            authority=source.authority,
            title=doc.title,
            url=chunk.url,
            citation_label=chunk.citation_label,
            content_sha256=chunk.content_sha256,
        ))

    header = (
        "Conhecimento JURIDICO OFICIAL verificado. Use APENAS as fontes abaixo "
        "para afirmar norma, jurisprudencia, regra de prazo ou informacao juridica. "
        "Cite a autoridade e a URL. Se as fontes abaixo nao resolverem a pergunta, "
        "diga que nao encontrou fonte oficial suficiente."
    )
    return LegalRetrievalResult(
        looks_legal=True,
        context=header + "\n\n" + "\n\n---\n\n".join(blocks),
        citations=citations,
    )


def _rank_rows(rows: Iterable[tuple], query_tokens: List[str]) -> List[tuple]:
    ranked = []
    query_set = set(query_tokens)
    for chunk, doc, source in rows:
        haystack = _normalize(" ".join([
            chunk.content or "",
            chunk.heading or "",
            doc.title or "",
            source.source_key or "",
            source.title or "",
            source.authority or "",
        ]))
        doc_tokens = set(_tokens(haystack))
        overlap = len(query_set.intersection(doc_tokens))
        if overlap <= 0:
            continue
        score = float(overlap)
        score += _article_number_boost(" ".join([chunk.heading or "", chunk.content or ""]), query_tokens)
        score += _source_alias_boost(query_set, doc.title or "", source.source_key or "", source.title or "")
        if (chunk.heading or "").lower().startswith("art"):
            score += 0.5
        if any(tok in _normalize(doc.title or "") for tok in query_set):
            score += 0.25
        ranked.append((chunk, doc, source, score))
    ranked.sort(key=lambda item: item[3], reverse=True)
    return ranked
