#!/usr/bin/env python3
"""Benchmark dashboard.html cold render versus filesystem bytecode-cache render."""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.smoke_jinja_bytecode_cache import (  # noqa: E402
    build_dashboard_context,
    build_templates,
    cache_files,
    render_dashboard,
    reset_cache_dir,
)


def _render_ms(templates, template_name: str, context: dict) -> float:
    templates.env.cache.clear()
    started = time.perf_counter()
    render_dashboard(templates, template_name, context)
    return (time.perf_counter() - started) * 1000


def run_benchmark(
    runs: int,
    cache_dir: Path,
    template_name: str,
    product: str,
    min_reduction_pct: float | None,
) -> int:
    cold_times = []
    warm_times = []

    for _ in range(runs):
        reset_cache_dir(cache_dir)
        templates = build_templates(cache_dir, product=product)
        context = build_dashboard_context(product=product)

        cold_times.append(_render_ms(templates, template_name, context))
        if not cache_files(cache_dir):
            print("ERROR: cold render did not create __jinja2_*.cache files", file=sys.stderr)
            return 1
        warm_times.append(_render_ms(templates, template_name, context))

    cold_avg = statistics.mean(cold_times)
    warm_avg = statistics.mean(warm_times)
    reduction = ((cold_avg - warm_avg) / cold_avg * 100) if cold_avg else 0
    files = cache_files(cache_dir)

    print(f"template={template_name}")
    print(f"product={product}")
    print(f"runs={runs}")
    print(f"cold_ms_avg={cold_avg:.2f}")
    print(f"warm_ms_avg={warm_avg:.2f}")
    print(f"reduction_pct={reduction:.2f}")
    print(f"cache_dir={cache_dir}")
    print(f"cache_files={len(files)}")
    for idx, (cold, warm) in enumerate(zip(cold_times, warm_times), start=1):
        print(f"run_{idx}=cold_ms:{cold:.2f},warm_ms:{warm:.2f}")

    if min_reduction_pct is not None and reduction < min_reduction_pct:
        print(
            f"ERROR: reduction_pct {reduction:.2f} below required {min_reduction_pct:.2f}",
            file=sys.stderr,
        )
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/casehub-jinja-benchmark"))
    parser.add_argument("--template", default="dashboard.html")
    parser.add_argument("--product", choices=("lite", "immigration"), default="lite")
    parser.add_argument("--min-reduction-pct", type=float, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_benchmark(
        args.runs,
        args.cache_dir,
        args.template,
        args.product,
        args.min_reduction_pct,
    )


if __name__ == "__main__":
    raise SystemExit(main())
