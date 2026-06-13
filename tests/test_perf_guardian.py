from types import SimpleNamespace

import pytest


def test_percentile_uses_nearest_rank():
    from scripts.perf_guardian import percentile

    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([10, 20, 30, 40], 50) == 20


def test_route_verdict_fails_on_ttfb_total_and_size():
    from scripts.perf_guardian import RouteSample, summarize_samples

    summary = summarize_samples(
        [RouteSample(status_code=200, total_ms=3000, ttfb_ms=900, bytes=2_000_000)],
        size_budget_bytes=900_000,
    )

    assert summary["verdict"]["status"] == "fail"
    assert any("ttfb_p95_ms" in item for item in summary["verdict"]["failures"])
    assert any("total_p95_ms" in item for item in summary["verdict"]["failures"])
    assert any("bytes" in item for item in summary["verdict"]["failures"])


def test_report_markdown_contains_required_operational_fields():
    from scripts.perf_guardian import SCHEMA_VERSION, render_markdown

    report = {
        "schema_version": SCHEMA_VERSION,
        "sha": "abc123",
        "environment": {"base_url": "https://dev.vingren.me"},
        "tenant": {"slug": "perf-bench-dev"},
        "profile": {"name": "readme-min-current"},
        "verdict": {"status": "fail", "failures": []},
        "routes": [
            {
                "path": "/casehub/dashboard",
                "summary": {
                    "verdict": {"status": "pass", "failures": []},
                    "ttfb_ms": {"p95": 120},
                    "total_ms": {"p95": 300},
                    "bytes": {"max": 1000},
                },
            }
        ],
        "suggestions": ["dashboard: profile server-side DB/Jinja/auth path"],
    }

    markdown = render_markdown(report)

    assert "CaseHub Performance Guardian" in markdown
    assert "`abc123`" in markdown
    assert "`perf-bench-dev`" in markdown
    assert "/casehub/dashboard" in markdown


def test_seed_refuses_production_target():
    from scripts.perf_guardian import seed_perf_tenant

    with pytest.raises(SystemExit):
        seed_perf_tenant(SimpleNamespace(target="production", profile="readme-min-current", reset=True))


def test_perf_lead_marker_is_strict_to_synthetic_data():
    from scripts.perf_guardian import MANAGED_BY, is_perf_lead_marker

    assert is_perf_lead_marker(
        "perf-bench-00001",
        {
            "email": "lead@perf-bench.local",
            "managed_by": MANAGED_BY,
            "perf_bench": True,
        },
    )
    assert not is_perf_lead_marker(
        "perf-bench-00001",
        {"email": "lead@perf-bench.local"},
    )
    assert not is_perf_lead_marker(
        "abc",
        {"tags": ["perf-bench"], "email": "client@example.com"},
    )
    assert not is_perf_lead_marker("abc", {"email": "client@example.com", "tags": ["real-client"]})


def test_static_check_blocks_deploy_halt_path():
    from scripts.perf_guardian_static_check import check_paths

    failures = check_paths(["docs/security/deploy-halt.json"])

    assert failures
    assert "blocked path" in failures[0]
