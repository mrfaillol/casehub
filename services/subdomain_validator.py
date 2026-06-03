"""
CaseHub - Subdomain validator.

Centralizes slug validation for self-service signup and the setup wizard.
Three checks (in order, cheapest first):
  1. Format (regex)
  2. Reserved blocklist (DB-backed, seeded in migration 2026-05-24)
  3. Collision with existing Organization.slug (case-insensitive)

Returns a structured `SubdomainCheck` so the API layer can render errors and
suggestions consistently.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models.tenant import Organization


# Format rule:
#   - lowercase letters, digits, hyphens
#   - 3..63 chars total
#   - must start with a letter
#   - must NOT end with a hyphen
#   - no double hyphens
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,61}[a-z0-9]$")
_DOUBLE_HYPHEN_RE = re.compile(r"--+")


@dataclass
class SubdomainCheck:
    """Result of a slug validation."""

    available: bool
    reason: str  # 'ok' | 'invalid' | 'reserved' | 'taken'
    message: str
    suggestions: List[str] = field(default_factory=list)
    canonical_slug: Optional[str] = None  # the normalized/slugified form

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "reason": self.reason,
            "message": self.message,
            "suggestions": self.suggestions,
            "canonical_slug": self.canonical_slug,
        }


def slugify(name: str) -> str:
    """Convert a firm name into a canonical slug.

    Postel's law applied: accept liberal input, emit strict output.
    Example: 'Silva & Advogados S/S Ltda' -> 'silva-advogados-s-s-ltda'
    """
    if not name:
        return ""

    # Unicode normalize: strip accents (NFD then drop combining marks)
    normalized = unicodedata.normalize("NFD", name)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))

    s = ascii_only.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", " ", s)  # any other char becomes a separator
    s = re.sub(r"[\s_]+", "-", s)         # whitespace/underscore -> hyphen
    s = _DOUBLE_HYPHEN_RE.sub("-", s)
    s = s.strip("-")

    # Guarantee a letter at the start (regex anchor)
    if s and not s[0].isalpha():
        s = "a" + s

    return s[:63] if s else ""


def is_valid_format(slug: str) -> bool:
    """Cheap regex-only check; does not hit the DB."""
    if not slug or len(slug) < 3 or len(slug) > 63:
        return False
    if _DOUBLE_HYPHEN_RE.search(slug):
        return False
    return bool(_SLUG_RE.match(slug))


def is_reserved(db: Session, slug: str) -> bool:
    """Check the reserved_subdomains seed table."""
    row = db.execute(
        text("SELECT 1 FROM reserved_subdomains WHERE slug = :s LIMIT 1"),
        {"s": slug},
    ).first()
    return row is not None


def is_taken(db: Session, slug: str) -> bool:
    """Check if an existing organization already owns the slug (case-insensitive)."""
    existing = (
        db.query(Organization)
        .filter(func.lower(Organization.slug) == slug.lower())
        .first()
    )
    return existing is not None


def suggest_alternatives(db: Session, base_slug: str, limit: int = 5) -> List[str]:
    """Generate alternative slugs when the requested one is taken/reserved.

    Strategy:
      - base + '-adv', '-advs', '-law', '-sp', '-rj'
      - base + '2', '3', ...
      - base truncated + sequential
    Only returns slugs that pass all three checks.
    """
    suffixes = ["-adv", "-advs", "-law", "-sp", "-rj", "-br", "-pro", "-co", "-grp"]
    suffixes += [f"-{n}" for n in range(2, 10)]
    suffixes += [str(n) for n in range(2, 10)]

    out: List[str] = []
    seen = {base_slug}

    for suf in suffixes:
        candidate = (base_slug + suf)[:63].rstrip("-")
        if candidate in seen or not is_valid_format(candidate):
            continue
        seen.add(candidate)
        if is_reserved(db, candidate) or is_taken(db, candidate):
            continue
        out.append(candidate)
        if len(out) >= limit:
            break

    return out


def check_subdomain(db: Session, raw_input: str) -> SubdomainCheck:
    """Full validation pipeline. Cheapest checks first.

    `raw_input` can be the firm name (we'll slugify) or an already-slugified value.
    """
    if not raw_input or not raw_input.strip():
        return SubdomainCheck(
            available=False,
            reason="invalid",
            message="Informe um nome ou subdomínio.",
            canonical_slug=None,
        )

    # Slugify if it looks non-canonical (contains uppercase, spaces, punctuation)
    if raw_input != raw_input.lower() or " " in raw_input or any(c in raw_input for c in "&./_"):
        slug = slugify(raw_input)
    else:
        slug = raw_input.lower().strip()

    if not is_valid_format(slug):
        return SubdomainCheck(
            available=False,
            reason="invalid",
            message=(
                "Subdomínio precisa ter entre 3 e 63 caracteres, começar com letra, "
                "usar apenas letras minúsculas, números e hífens. Sem hífen duplo, "
                "sem hífen no final."
            ),
            canonical_slug=slug or None,
        )

    if is_reserved(db, slug):
        return SubdomainCheck(
            available=False,
            reason="reserved",
            message="Este subdomínio é reservado pelo sistema. Escolha outro.",
            suggestions=suggest_alternatives(db, slug),
            canonical_slug=slug,
        )

    if is_taken(db, slug):
        return SubdomainCheck(
            available=False,
            reason="taken",
            message="Este subdomínio já está em uso por outro escritório.",
            suggestions=suggest_alternatives(db, slug),
            canonical_slug=slug,
        )

    return SubdomainCheck(
        available=True,
        reason="ok",
        message=f"{slug}.casehub.legal está disponível.",
        canonical_slug=slug,
    )
