from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vps_deploy_fails_closed_when_halt_file_is_missing():
    script = (ROOT / "scripts" / "vps-deploy.sh").read_text(encoding="utf-8")

    assert 'halt_fail "HALT file missing at $HALT_FILE"' in script
    assert 'log_line "WARN: HALT file missing' not in script


def test_vps_deploy_checks_out_exact_target_sha():
    script = (ROOT / "scripts" / "vps-deploy.sh").read_text(encoding="utf-8")

    assert 'TARGET_SHA_FULL=$(git rev-parse "$TARGET_SHA^{commit}")' in script
    assert 'git merge-base --is-ancestor "$TARGET_SHA_FULL" origin/main' in script
    assert 'git checkout -B main "$TARGET_SHA_FULL"' in script
    assert '[ "$HEAD_SHA" = "$TARGET_SHA_FULL" ]' in script
    assert "git pull --ff-only origin main" not in script


def test_vps_deploy_requires_clean_untracked_context_and_excludes_markers():
    script = (ROOT / "scripts" / "vps-deploy.sh").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "git status --porcelain --untracked-files=all" in script
    assert ".deploy-*" in dockerignore
    assert ".previous-sha" in dockerignore


def test_vps_deploy_markers_are_gitignored():
    gitignore_lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    present = {
        line.strip()
        for line in gitignore_lines
        if line.strip() and not line.strip().startswith("#")
    }
    expected_markers = {
        ".deploy-sha",
        ".deploy-timestamp",
        ".deploy-actor",
        ".previous-sha",
        ".bootstrap-log",
    }
    missing = expected_markers - present

    assert not missing, (
        "deploy markers missing from .gitignore; they would pollute "
        "`git status --porcelain --untracked-files=all` and abort the next "
        f"deploy: {sorted(missing)}"
    )


def test_vps_deploy_does_not_accept_halt_override_from_environment():
    script = (ROOT / "scripts" / "vps-deploy.sh").read_text(encoding="utf-8")

    assert 'HALT_OVERRIDE_ISSUE=""' in script
    assert 'HALT_OVERRIDE_REASON=""' in script
    assert "CASEHUB_DEPLOY_HALT_OVERRIDE_ISSUE" not in script
    assert "CASEHUB_DEPLOY_HALT_OVERRIDE_REASON" not in script
