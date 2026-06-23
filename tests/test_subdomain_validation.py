"""
Unit tests for services.subdomain_validator.

Covers:
  - slugify (accent stripping, punctuation collapse, edge cases)
  - is_valid_format (regex boundaries)
  - reserved-list rejection
  - case-insensitive collision detection
  - suggestion generation
  - full check_subdomain pipeline
"""
import pytest
from sqlalchemy import text

from models.reserved import ReservedSubdomain
from models.tenant import Organization
from services.subdomain_validator import (
    check_subdomain,
    is_valid_format,
    is_reserved,
    is_taken,
    slugify,
    suggest_alternatives,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_reserved(db):
    """Seed a small reserved set sufficient for these tests."""
    for slug, reason in [
        ("admin", "security"),
        ("api", "reserved_app"),
        ("www", "infrastructure"),
        ("example-law", "reserved_example"),
        ("casehub", "brand_casehub"),
    ]:
        db.add(ReservedSubdomain(slug=slug, reason=reason))
    db.commit()


@pytest.fixture
def seed_existing_org(db):
    """Seed an existing organization that owns the slug 'silva-adv'."""
    org = Organization(
        uuid="00000000-0000-0000-0000-000000000001",
        name="Silva Advogados",
        slug="silva-adv",
        plan="starter",
    )
    db.add(org)
    db.commit()


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic_lowercase(self):
        assert slugify("Silva Advogados") == "silva-advogados"

    def test_strips_accents(self):
        assert slugify("Vinícius & Sócios") == "vinicius-socios"

    def test_collapses_punctuation(self):
        assert slugify("Silva & Sá / Advs. Ltda.") == "silva-sa-advs-ltda"

    def test_no_leading_digit(self):
        # Must start with a letter — leading digit gets prefixed with 'a'
        assert slugify("123 Lawyers").startswith("a")

    def test_truncates_to_63(self):
        long_name = "a" * 200
        assert len(slugify(long_name)) == 63

    def test_empty_input(self):
        assert slugify("") == ""
        assert slugify("   ") == ""

    def test_only_special_chars(self):
        # Returns empty when nothing alphanumeric survives
        assert slugify("&&&///") == ""

    def test_collapses_double_hyphens(self):
        assert slugify("Silva   --   Sá") == "silva-sa"

    def test_strips_edge_hyphens(self):
        assert not slugify("---silva---").startswith("-")
        assert not slugify("---silva---").endswith("-")


# ---------------------------------------------------------------------------
# is_valid_format (regex-only, no DB)
# ---------------------------------------------------------------------------

class TestIsValidFormat:
    @pytest.mark.parametrize("slug", [
        "silva",
        "silva-adv",
        "abc",
        "casehub123",
        "a-b-c-d-e-f",
        "abc-d2",
    ])
    def test_valid(self, slug):
        assert is_valid_format(slug) is True

    @pytest.mark.parametrize("slug", [
        "",                # empty
        "ab",              # too short (<3)
        "1silva",          # starts with digit
        "-silva",          # starts with hyphen
        "silva-",          # ends with hyphen
        "Silva",           # uppercase
        "silva_adv",       # underscore not allowed
        "silva.adv",       # dot not allowed
        "silva  adv",      # space
        "silva--adv",      # double hyphen
        "a" * 64,          # too long (>63)
    ])
    def test_invalid(self, slug):
        assert is_valid_format(slug) is False


# ---------------------------------------------------------------------------
# is_reserved
# ---------------------------------------------------------------------------

class TestIsReserved:
    def test_reserved_returns_true(self, db, seed_reserved):
        assert is_reserved(db, "admin") is True
        assert is_reserved(db, "api") is True
        assert is_reserved(db, "example-law") is True

    def test_non_reserved_returns_false(self, db, seed_reserved):
        assert is_reserved(db, "silva-adv") is False
        assert is_reserved(db, "novo-escritorio") is False


# ---------------------------------------------------------------------------
# is_taken (case-insensitive)
# ---------------------------------------------------------------------------

class TestIsTaken:
    def test_existing_slug_is_taken(self, db, seed_existing_org):
        assert is_taken(db, "silva-adv") is True

    def test_case_insensitive(self, db, seed_existing_org):
        assert is_taken(db, "Silva-Adv") is True
        assert is_taken(db, "SILVA-ADV") is True

    def test_unused_slug(self, db, seed_existing_org):
        assert is_taken(db, "outro-escritorio") is False


# ---------------------------------------------------------------------------
# suggest_alternatives
# ---------------------------------------------------------------------------

class TestSuggestAlternatives:
    def test_returns_alternatives_when_base_taken(self, db, seed_existing_org, seed_reserved):
        suggestions = suggest_alternatives(db, "silva-adv", limit=3)
        assert len(suggestions) <= 3
        assert "silva-adv" not in suggestions  # never suggests the original
        for s in suggestions:
            assert is_valid_format(s)
            assert not is_taken(db, s)
            assert not is_reserved(db, s)

    def test_skips_reserved_suffixes(self, db, seed_reserved):
        # 'api' is reserved; suggestions for 'api' must not include 'api' itself
        suggestions = suggest_alternatives(db, "api", limit=5)
        assert "api" not in suggestions


# ---------------------------------------------------------------------------
# check_subdomain (full pipeline)
# ---------------------------------------------------------------------------

class TestCheckSubdomain:
    def test_ok_when_available(self, db, seed_reserved):
        result = check_subdomain(db, "novo-escritorio")
        assert result.available is True
        assert result.reason == "ok"
        assert result.canonical_slug == "novo-escritorio"

    def test_slugifies_natural_input(self, db, seed_reserved):
        result = check_subdomain(db, "Silva & Advogados S/S")
        assert result.canonical_slug == "silva-advogados-s-s"
        # And since 'silva-advogados-s-s' isn't reserved/taken, it's available
        assert result.available is True

    def test_rejects_invalid_format(self, db, seed_reserved):
        result = check_subdomain(db, "ab")  # too short
        assert result.available is False
        assert result.reason == "invalid"

    def test_rejects_reserved(self, db, seed_reserved):
        result = check_subdomain(db, "admin")
        assert result.available is False
        assert result.reason == "reserved"
        assert len(result.suggestions) >= 1

    def test_rejects_taken(self, db, seed_reserved, seed_existing_org):
        result = check_subdomain(db, "silva-adv")
        assert result.available is False
        assert result.reason == "taken"
        assert len(result.suggestions) >= 1

    def test_empty_input(self, db, seed_reserved):
        result = check_subdomain(db, "")
        assert result.available is False
        assert result.reason == "invalid"

    def test_whitespace_only(self, db, seed_reserved):
        result = check_subdomain(db, "   ")
        assert result.available is False
        assert result.reason == "invalid"

    def test_to_dict_shape(self, db, seed_reserved):
        result = check_subdomain(db, "novo-escritorio")
        d = result.to_dict()
        assert set(d.keys()) == {"available", "reason", "message", "suggestions", "canonical_slug"}
