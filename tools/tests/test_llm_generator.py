#!/usr/bin/env python3
"""
Tests for LLM Content Generator
Validates document generation for LOR and PS.
"""

import pytest
import asyncio
import os
from unittest.mock import patch, AsyncMock

# python-docx is required by sibling modules (lor_generator, ps_generator)
pytest.importorskip("docx", reason="python-docx not installed")

# Add parent directory to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_content_generator import (
    generate_lor_content,
    generate_ps_content,
    get_field_references,
    get_unique_seed,
    parse_ps_sections,
    FIELD_REFERENCES,
    WRITING_STYLES,
    TONES,
)


# =============================================================================
# UNIT TESTS - No API calls
# =============================================================================

class TestFieldReferences:
    """Test field reference lookup."""

    def test_exact_match(self):
        """Test exact field match."""
        refs = get_field_references("cybersecurity")
        assert "executive_orders" in refs
        assert len(refs["executive_orders"]) > 0

    def test_partial_match(self):
        """Test partial field match."""
        refs = get_field_references("artificial_intelligence_ml")
        assert "statistics" in refs

    def test_normalized_match(self):
        """Test with spaces and hyphens."""
        refs = get_field_references("clean energy")
        assert "strategic_plans" in refs

        refs2 = get_field_references("clean-energy")
        assert "strategic_plans" in refs2

    def test_unknown_field(self):
        """Test unknown field returns defaults."""
        refs = get_field_references("underwater_basket_weaving")
        assert refs["executive_orders"] == []
        assert "Relevant federal strategic initiatives" in refs["strategic_plans"]

    def test_all_fields_have_required_keys(self):
        """Ensure all fields have required reference keys."""
        required_keys = ["executive_orders", "strategic_plans", "statistics"]
        for field, refs in FIELD_REFERENCES.items():
            for key in required_keys:
                assert key in refs, f"Field {field} missing {key}"


class TestUniqueSeed:
    """Test unique seed generation."""

    def test_seed_format(self):
        """Seed should be 8 character hex string."""
        seed = get_unique_seed()
        assert len(seed) == 8
        assert all(c in "0123456789abcdef" for c in seed)

    def test_seeds_are_unique(self):
        """Multiple calls should produce different seeds."""
        seeds = [get_unique_seed() for _ in range(10)]
        assert len(set(seeds)) == 10  # All unique


class TestParseSections:
    """Test PS section parsing."""

    def test_parse_standard_format(self):
        """Test parsing with standard Roman numeral format."""
        content = """
I. Overview of the Proposed Endeavor

This is the overview section content.

II. National Importance

This is the national importance section.

III. Practical Impact

This is the practical impact section.

IV. Well-Positioned

This is the well-positioned section.

V. Conclusion

This is the conclusion.
"""
        sections = parse_ps_sections(content)
        assert "overview" in sections["overview"].lower()
        assert "national" in sections["national_importance"].lower()
        assert "practical" in sections["practical_impact"].lower()
        assert "conclusion" in sections["conclusion"].lower()

    def test_fallback_on_unparseable(self):
        """Test fallback when content can't be parsed."""
        content = "This is just plain text without sections."
        sections = parse_ps_sections(content)
        assert sections["overview"] == content
        assert sections["national_importance"] == ""


class TestStylesAndTones:
    """Test style and tone configurations."""

    def test_styles_not_empty(self):
        """Writing styles should not be empty."""
        assert len(WRITING_STYLES) >= 5

    def test_tones_not_empty(self):
        """Tones should not be empty."""
        assert len(TONES) >= 5


# =============================================================================
# INTEGRATION TESTS - With mocked API
# =============================================================================

class TestLORGeneration:
    """Test LOR generation with mocked API."""

    @pytest.fixture
    def mock_gemini_response(self):
        """Mock successful Gemini response."""
        return """As a Senior Research Scientist at Toyota Research Institute with over fifteen years of experience in autonomous systems and human-robot interaction, I have had the unique opportunity to observe and evaluate some of the most talented engineers in our field.

My background includes a Ph.D. in Mechanical Engineering from Northwestern University, where I specialized in assistive robotics and machine learning applications for healthcare. During my tenure at the Shirley Ryan AbilityLab in Chicago, I developed groundbreaking algorithms for smart wheelchair navigation that have since been adopted by major rehabilitation centers across the United States.

I first encountered Jane Smith's work during her internship at our laboratory in 2023. Over the course of three months, I directly mentored her on a project focused on improving shared autonomy capabilities in smart wheelchairs. Her contributions were exceptional from the start.

The United States currently faces a critical shortage in robotics engineers, with the Bureau of Labor Statistics projecting a 25% increase in demand over the next decade. According to the National AI R&D Strategic Plan (2023 Update), advancing human-robot interaction remains a top priority for national competitiveness. Ms. Smith's work directly addresses these national priorities.

Her unique combination of theoretical knowledge and practical implementation skills sets her apart. She developed novel goal arbitration algorithms that reduced navigation errors by 47% while maintaining user autonomy. This dual capability is rare in the field.

Given the rapid advancement of AI and robotics technology, and the documented shortage of qualified professionals in this field, it would be in the national interest to waive the labor certification requirements for Ms. Smith. Her continued work in the United States will benefit American citizens with mobility impairments while advancing our nation's technological leadership.

I give my strongest possible recommendation for Jane Smith's EB-2 NIW petition and urge USCIS to recognize her exceptional contributions to this critically important field."""

    @pytest.mark.asyncio
    async def test_lor_generation_success(self, mock_gemini_response):
        """Test successful LOR generation."""
        with patch('llm_content_generator._call_gemini', new_callable=AsyncMock) as mock:
            mock.return_value = mock_gemini_response

            paragraphs = await generate_lor_content(
                beneficiary_name="Jane Smith",
                field="robotics",
                recommender_name="Dr. John Doe",
                recommender_title="Senior Research Scientist",
                recommender_org="Toyota Research Institute",
                recommender_email="john.doe@example.com",
                relationship="Mentor during internship",
                years_known="2 years",
            )

            assert len(paragraphs) > 0
            full_text = " ".join(paragraphs)
            assert len(full_text.split()) >= 300  # Should have substantial content

    @pytest.mark.asyncio
    async def test_lor_fallback_to_perplexity(self, mock_gemini_response):
        """Test fallback to Perplexity when Gemini fails."""
        with patch('llm_content_generator._call_gemini', new_callable=AsyncMock) as mock_gemini:
            mock_gemini.side_effect = Exception("Gemini API error")

            with patch('llm_content_generator._call_perplexity', new_callable=AsyncMock) as mock_pplx:
                mock_pplx.return_value = mock_gemini_response

                paragraphs = await generate_lor_content(
                    beneficiary_name="Jane Smith",
                    field="cybersecurity",
                    recommender_name="Dr. Security Expert",
                    recommender_title="CISO",
                    recommender_org="Major Bank",
                    recommender_email="ciso@example.com",
                    relationship="Direct supervisor",
                    years_known="5 years",
                )

                assert len(paragraphs) > 0
                mock_pplx.assert_called_once()


class TestPSGeneration:
    """Test PS generation with mocked API."""

    @pytest.fixture
    def mock_ps_response(self):
        """Mock successful PS response."""
        return """I. Overview of the Proposed Endeavor

My journey in the field of cybersecurity began during my undergraduate studies at MIT, where I developed a passion for protecting critical infrastructure from cyber threats. Over the past decade, I have dedicated my career to advancing the nation's cybersecurity posture through innovative research and practical implementations.

Currently, I serve as a Senior Security Architect at a Fortune 500 technology company, where I lead a team of twelve engineers in developing next-generation threat detection systems. My proposed endeavor in the United States encompasses three distinct components: advancing threat intelligence capabilities, developing AI-powered security solutions, and training the next generation of cybersecurity professionals.

II. National Importance of the Endeavor

Executive Order 14028, "Improving the Nation's Cybersecurity" (May 12, 2021), explicitly recognizes the critical importance of strengthening the nation's cyber defenses. The National Cybersecurity Strategy (March 2023) further emphasizes the need for innovative approaches to combat evolving threats.

According to the FBI, cybercrime losses exceeded $12.5 billion in 2023 alone. CyberSeek reports over 500,000 unfilled cybersecurity positions in the United States, representing a significant national security vulnerability.

III. Practical Impact and Innovation

My contributions to the field include three patents for novel intrusion detection algorithms, fifteen peer-reviewed publications with over 2,000 combined citations, and the development of an open-source security framework used by over 10,000 organizations worldwide.

IV. Why I Am Well-Positioned to Advance the Endeavor

My unique combination of academic credentials and industry experience positions me exceptionally well to advance this endeavor. I hold a Ph.D. in Computer Science from Stanford University, with a specialization in network security and machine learning.

V. Conclusion

In summary, my proposed endeavor offers a twofold benefit to the United States: strengthening national cybersecurity infrastructure while developing the skilled workforce needed to maintain our technological leadership.

I declare under penalty of perjury under the laws of the United States of America that the foregoing is true and correct.

Signed: [Name]
Date: [Current Date]"""

    @pytest.mark.asyncio
    async def test_ps_generation_success(self, mock_ps_response):
        """Test successful PS generation."""
        with patch('llm_content_generator._call_gemini', new_callable=AsyncMock) as mock:
            mock.return_value = mock_ps_response

            sections = await generate_ps_content(
                beneficiary_name="John Cybersec",
                field="cybersecurity",
                overview="I am a senior security architect with 10 years experience",
            )

            assert "overview" in sections
            assert "national_importance" in sections
            assert "conclusion" in sections
            assert len(sections["overview"]) > 0

    @pytest.mark.asyncio
    async def test_ps_includes_perjury_declaration(self, mock_ps_response):
        """Test that PS includes perjury declaration."""
        with patch('llm_content_generator._call_gemini', new_callable=AsyncMock) as mock:
            mock.return_value = mock_ps_response

            sections = await generate_ps_content(
                beneficiary_name="Test User",
                field="ai_ml",
            )

            conclusion = sections.get("conclusion", "")
            assert "perjury" in conclusion.lower() or "penalty" in conclusion.lower()


# =============================================================================
# LIVE INTEGRATION TESTS (require API keys)
# =============================================================================

@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY") and not os.getenv("PERPLEXITY_API_KEY"),
    reason="No API keys configured"
)
class TestLiveAPI:
    """Live API tests - only run when API keys are available."""

    @pytest.mark.asyncio
    async def test_live_lor_generation(self):
        """Test actual LOR generation with live API."""
        paragraphs = await generate_lor_content(
            beneficiary_name="Test Beneficiary",
            field="ai_ml",
            recommender_name="Dr. Test Recommender",
            recommender_title="Professor",
            recommender_org="Test University",
            recommender_email="test@example.com",
            relationship="Academic advisor",
            years_known="3 years",
        )

        full_text = " ".join(paragraphs)
        word_count = len(full_text.split())

        assert word_count >= 500, f"LOR too short: {word_count} words"
        assert word_count <= 1200, f"LOR too long: {word_count} words"
        print(f"\n✓ Live LOR generated: {word_count} words")

    @pytest.mark.asyncio
    async def test_live_ps_generation(self):
        """Test actual PS generation with live API."""
        sections = await generate_ps_content(
            beneficiary_name="Test Beneficiary",
            field="cybersecurity",
            overview="I am a cybersecurity professional with expertise in threat detection.",
        )

        total_words = sum(len(s.split()) for s in sections.values())

        assert total_words >= 1500, f"PS too short: {total_words} words"
        print(f"\n✓ Live PS generated: {total_words} words")


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
