#!/usr/bin/env python3
"""
CaseHub Startup Benchmark
Measures import time, app creation, DB init, and memory usage.

Usage:
    python benchmark_startup.py
    python benchmark_startup.py --product immigration
    python benchmark_startup.py --product lite --runs 5
"""
import argparse
import os
import sys
import time
import tracemalloc

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tabulate import tabulate


def measure_import():
    """Measure time to import the app module."""
    # Clear any cached imports
    mods_to_remove = [k for k in sys.modules if k.startswith(("core.", "models.", "routes.", "services."))]
    for m in mods_to_remove:
        del sys.modules[m]
    if "app" in sys.modules:
        del sys.modules["app"]

    start = time.perf_counter()
    import core.app_factory  # noqa: F401
    elapsed = time.perf_counter() - start
    return elapsed


def measure_create_app(product: str):
    """Measure time to call create_app()."""
    from core.app_factory import create_app
    start = time.perf_counter()
    app = create_app(product)
    elapsed = time.perf_counter() - start
    return elapsed, app


def measure_init_db():
    """Measure time to call init_db()."""
    from models import init_db
    start = time.perf_counter()
    init_db()
    elapsed = time.perf_counter() - start
    return elapsed


def measure_memory():
    """Measure current memory usage after startup via tracemalloc."""
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.statistics("lineno")
    total_bytes = sum(s.size for s in stats)
    return total_bytes, stats[:10]  # total + top 10 allocators


def run_benchmark(product: str, runs: int):
    print(f"CaseHub Startup Benchmark")
    print(f"  Product: {product}")
    print(f"  Runs:    {runs}")
    print()

    import_times = []
    create_times = []
    initdb_times = []
    memory_samples = []

    for i in range(runs):
        print(f"  Run {i + 1}/{runs}...", end=" ", flush=True)

        # Start memory tracking
        tracemalloc.start()

        # 1. Import
        t_import = measure_import()
        import_times.append(t_import)

        # 2. create_app()
        t_create, app = measure_create_app(product)
        create_times.append(t_create)

        # 3. init_db()
        t_initdb = measure_init_db()
        initdb_times.append(t_initdb)

        # 4. Memory
        total_bytes, top_stats = measure_memory()
        memory_samples.append(total_bytes)

        tracemalloc.stop()

        total = t_import + t_create + t_initdb
        print(f"total={total * 1000:.0f}ms  mem={total_bytes / 1024 / 1024:.1f}MB")

        # Clean up for next run
        mods_to_remove = [k for k in sys.modules if k.startswith(("core.", "models.", "routes.", "services.", "auth", "config"))]
        for m in mods_to_remove:
            try:
                del sys.modules[m]
            except KeyError:
                pass

    print()

    # Summary table
    def stats_row(label, values, unit="ms", multiplier=1000):
        import statistics
        vals = [v * multiplier for v in values]
        return [
            label,
            f"{statistics.mean(vals):.1f}{unit}",
            f"{statistics.median(vals):.1f}{unit}",
            f"{min(vals):.1f}{unit}",
            f"{max(vals):.1f}{unit}",
        ]

    rows = [
        stats_row("Import core.app_factory", import_times),
        stats_row("create_app()", create_times),
        stats_row("init_db()", initdb_times),
        stats_row("Total startup", [a + b + c for a, b, c in zip(import_times, create_times, initdb_times)]),
    ]

    headers = ["Phase", "Avg", "Median", "Min", "Max"]
    print("=" * 70)
    print("TIMING RESULTS")
    print("=" * 70)
    print(tabulate(rows, headers=headers, tablefmt="grid"))
    print()

    # Memory summary
    import statistics
    mem_mb = [b / 1024 / 1024 for b in memory_samples]
    print("MEMORY (after full startup):")
    print(f"  Average: {statistics.mean(mem_mb):.2f} MB")
    print(f"  Min:     {min(mem_mb):.2f} MB")
    print(f"  Max:     {max(mem_mb):.2f} MB")
    print()

    # Top memory allocators from last run
    if runs > 0:
        tracemalloc.start()
        measure_import()
        measure_create_app(product)
        measure_init_db()
        _, top_stats = measure_memory()
        tracemalloc.stop()

        print("TOP 10 MEMORY ALLOCATIONS (last run):")
        for stat in top_stats:
            print(f"  {stat}")
        print()


def parse_args():
    parser = argparse.ArgumentParser(description="CaseHub Startup Benchmark")
    parser.add_argument("--product", default="immigration", help="Product type (default: immigration)")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs (default: 3)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_benchmark(args.product, args.runs)
