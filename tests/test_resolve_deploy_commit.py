import os
import tempfile

from core.app_factory import resolve_deploy_commit


def setup_function(_func):
    # Each test should see a fresh cache so file-system fixtures take effect.
    resolve_deploy_commit.cache_clear()


def test_returns_unknown_when_no_markers():
    with tempfile.TemporaryDirectory() as td:
        assert resolve_deploy_commit(td) == "unknown"


def test_prefers_deploy_info_over_stale_deploy_sha():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".deploy-info"), "w", encoding="utf-8") as fh:
            fh.write(
                "commit=af16b5a9ddb1f0ca91046a9658d479f4bbe658f3\n"
                "deployed_at=2026-05-04T21:48:10Z\n"
                "source=github-actions-main\n"
            )
        with open(os.path.join(td, ".deploy-sha"), "w", encoding="utf-8") as fh:
            fh.write("5ab3e29\n")
        assert (
            resolve_deploy_commit(td)
            == "af16b5a9ddb1f0ca91046a9658d479f4bbe658f3"
        )


def test_falls_back_to_deploy_sha_when_deploy_info_absent():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".deploy-sha"), "w", encoding="utf-8") as fh:
            fh.write("af16b5a9ddb1f0ca91046a9658d479f4bbe658f3\n")
        assert (
            resolve_deploy_commit(td)
            == "af16b5a9ddb1f0ca91046a9658d479f4bbe658f3"
        )


def test_falls_back_to_version_commit_when_others_absent():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "VERSION_COMMIT"), "w", encoding="utf-8") as fh:
            fh.write("1234567\n")
        assert resolve_deploy_commit(td) == "1234567"


def test_skips_malformed_deploy_info_and_uses_deploy_sha():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".deploy-info"), "w", encoding="utf-8") as fh:
            fh.write("deployed_at=2026-05-04T00:00:00Z\nsource=foo\n")
        with open(os.path.join(td, ".deploy-sha"), "w", encoding="utf-8") as fh:
            fh.write("af16b5a\n")
        assert resolve_deploy_commit(td) == "af16b5a"


def test_skips_non_utf8_deploy_info_and_uses_deploy_sha():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".deploy-info"), "wb") as fh:
            fh.write(b"commit=\xff\xfe\xfd\n")
        with open(os.path.join(td, ".deploy-sha"), "w", encoding="utf-8") as fh:
            fh.write("af16b5a\n")
        assert resolve_deploy_commit(td) == "af16b5a"


def test_empty_deploy_info_commit_falls_through():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".deploy-info"), "w", encoding="utf-8") as fh:
            fh.write("commit=\nsource=foo\n")
        with open(os.path.join(td, ".deploy-sha"), "w", encoding="utf-8") as fh:
            fh.write("af16b5a\n")
        assert resolve_deploy_commit(td) == "af16b5a"


def test_skips_non_utf8_deploy_sha_and_uses_version_commit():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".deploy-sha"), "wb") as fh:
            fh.write(b"\xff\xfe\xfd")
        with open(os.path.join(td, "VERSION_COMMIT"), "w", encoding="utf-8") as fh:
            fh.write("1234567\n")
        assert resolve_deploy_commit(td) == "1234567"


def test_result_is_cached_after_first_resolution():
    """Second call must not touch disk — health checks call this per request."""
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".deploy-sha"), "w", encoding="utf-8") as fh:
            fh.write("cached-sha\n")
        first = resolve_deploy_commit(td)
        # Mutate the marker on disk; cached value should remain.
        with open(os.path.join(td, ".deploy-sha"), "w", encoding="utf-8") as fh:
            fh.write("changed-after-cache\n")
        second = resolve_deploy_commit(td)
        assert first == "cached-sha"
        assert second == "cached-sha"
        # Sanity-check: clearing the cache picks up the new value.
        resolve_deploy_commit.cache_clear()
        assert resolve_deploy_commit(td) == "changed-after-cache"
