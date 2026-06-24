from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_alpha_compose_persists_runtime_upload_roots_only_in_alpha_override():
    alpha = (ROOT / "docker-compose.alpha.yml").read_text(encoding="utf-8")
    base = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "casehub_uploads:/app/uploads" in alpha
    assert "casehub_data_uploads:/app/data/uploads" in alpha
    assert "name: casehub_uploads" in alpha
    assert "name: casehub_data_uploads" in alpha
    assert "./uploads:/app/uploads" in base
    assert "casehub_uploads:/app/uploads" not in base


def test_alpha_workflow_protects_runtime_state_from_rsync_and_concurrency():
    workflow = (ROOT / ".github/workflows/deploy-alpha.yml").read_text(encoding="utf-8")

    assert 'CASEHUB_RUNTIME_ORG_IDS: "4"' in workflow
    assert "Acquire alpha deploy lock" in workflow
    assert ".deploy.lockdir" in workflow
    assert "Release alpha deploy lock" in workflow
    assert workflow.index("Release alpha deploy lock") < workflow.index("Clean SSH key")
    assert "--exclude 'uploads/'" in workflow
    assert "--exclude 'data/'" in workflow
    assert "--exclude '.wwebjs_auth/'" in workflow
    assert "--exclude 'tmp/'" in workflow


def test_alpha_workflow_seeds_runtime_volumes_once():
    workflow = (ROOT / ".github/workflows/deploy-alpha.yml").read_text(encoding="utf-8")

    assert "seed_runtime_volume casehub_uploads /app/uploads" in workflow
    assert "seed_runtime_volume casehub_data_uploads /app/data/uploads" in workflow
    assert "casehub-app:\\$target/." in workflow
    assert "cp -a /runtime-seed/." in workflow
    assert "cp -an /runtime-seed/." not in workflow
    assert ".casehub-runtime-seeded" in workflow
    assert "CASEHUB_RUNTIME_SEED_IMAGE:-alpine:latest" in workflow
    assert "CASEHUB_RUNTIME_TARGET" in workflow
    assert workflow.count("touch \"\\$CASEHUB_RUNTIME_TARGET/.casehub-runtime-seeded\"") >= 2
    assert '"$1/.casehub-runtime-seeded"' not in workflow
