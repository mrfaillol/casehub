#!/usr/bin/env python3
"""
Tests for Intake Link Generation and Validation
Ensures intake links are correctly formatted and accessible before sending to clients.
"""

import pytest
import uuid
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.intake_service import intake_service
from services.intake_email_service import validate_link_before_sending


class TestLinkGeneration:
    """Test intake link generation."""

    def test_generate_link_format(self):
        """Test that generated links have correct format."""
        package_id = "TEST-PKG-01"
        token = str(uuid.uuid4())
        base_url = "https://app.casehub.io"

        link = intake_service.generate_client_link(package_id, token, base_url)

        # Should have format: https://app.casehub.io/intake/{package_id}?token={token}
        assert link.startswith(f"{base_url}/intake/")
        assert package_id in link
        assert f"token={token}" in link

    def test_generate_link_no_casehub_prefix(self):
        """Test that generated links do NOT include /casehub/portal/ prefix."""
        package_id = "TEST-PKG-02"
        token = str(uuid.uuid4())

        link = intake_service.generate_client_link(package_id, token)

        # Should NOT have /casehub/portal/ in the path
        assert "/casehub/portal/" not in link
        assert "/casehub/portal/intake/" not in link

        # Should have correct /intake/ prefix only
        assert "/intake/" in link

    def test_generate_multiple_links_unique(self):
        """Test that generating multiple links produces unique tokens."""
        links = []
        for i in range(10):
            package_id = f"PKG-{i:02d}"
            token = str(uuid.uuid4())
            link = intake_service.generate_client_link(package_id, token)
            links.append(link)

        # All links should be unique
        assert len(links) == len(set(links))

    def test_generate_link_with_custom_base_url(self):
        """Test link generation with custom base URL."""
        package_id = "TEST-PKG-03"
        token = str(uuid.uuid4())
        custom_base = "https://staging.casehub.io"

        link = intake_service.generate_client_link(package_id, token, custom_base)

        assert link.startswith(custom_base)
        assert "/intake/" in link


class TestLinkValidation:
    """Test intake link validation functionality."""

    def test_validate_invalid_url(self):
        """Test validation fails for invalid URLs."""
        result = validate_link_before_sending("https://invalid-domain-that-does-not-exist-12345.com")

        assert result["valid"] is False
        assert result["error"] is not None

    def test_validate_malformed_url(self):
        """Test validation fails for malformed URLs."""
        result = validate_link_before_sending("not-a-url")

        assert result["valid"] is False
        assert result["error"] is not None

    def test_validate_timeout_handling(self):
        """Test that validation handles timeouts gracefully."""
        # Use a URL that will timeout (non-routable IP)
        result = validate_link_before_sending("http://10.255.255.1", timeout=1)

        assert result["valid"] is False
        assert result["error"] is not None

    @pytest.mark.skip(reason="Requires actual server running - run manually")
    def test_validate_real_link(self):
        """
        Test validation with a real intake link.
        NOTE: This test is skipped by default as it requires the actual server to be running.
        Run manually with: pytest -v -k test_validate_real_link -m "not skip"
        """
        # This would require a real package ID and token from the database
        test_link = "https://app.casehub.io/intake/TEST-123?token=test-token"
        result = validate_link_before_sending(test_link)

        # When server is running and link exists, should be valid
        assert result["status_code"] is not None


class TestLinkFormat:
    """Test link format specifications."""

    def test_link_has_https(self):
        """Test that links use HTTPS protocol."""
        package_id = "TEST-PKG-04"
        token = str(uuid.uuid4())
        base_url = "https://app.casehub.io"

        link = intake_service.generate_client_link(package_id, token, base_url)

        assert link.startswith("https://")

    def test_link_has_query_parameter(self):
        """Test that links include token as query parameter."""
        package_id = "TEST-PKG-05"
        token = str(uuid.uuid4())

        link = intake_service.generate_client_link(package_id, token)

        assert "?" in link
        assert "token=" in link

    def test_link_package_id_preserved(self):
        """Test that package ID is correctly preserved in URL."""
        package_id = "SANAA-I765-01"
        token = "TEST-TOKEN-PACKAGE-ID"

        link = intake_service.generate_client_link(package_id, token)

        # Package ID should appear in the path
        assert package_id in link
        assert link.count(package_id) == 1  # Should appear exactly once


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
