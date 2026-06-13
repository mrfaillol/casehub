#!/usr/bin/env python3
"""
CaseHub API Benchmark
Load-tests key API endpoints using async httpx.

Usage:
    python benchmark_api.py --base-url http://localhost:8001 --email admin@example.com --password secret
    python benchmark_api.py --base-url http://localhost:8001 --email admin@example.com --password secret -n 200 --concurrency 10
"""
import argparse
import asyncio
import io
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx
from tabulate import tabulate

PREFIX = "/casehub"


@dataclass
class BenchmarkResult:
    endpoint: str
    method: str
    times: list = field(default_factory=list)
    errors: int = 0
    status_codes: dict = field(default_factory=dict)

    @property
    def count(self):
        return len(self.times)

    @property
    def avg(self):
        return statistics.mean(self.times) if self.times else 0

    @property
    def p50(self):
        return statistics.median(self.times) if self.times else 0

    @property
    def p95(self):
        return self._percentile(95)

    @property
    def p99(self):
        return self._percentile(99)

    @property
    def min_t(self):
        return min(self.times) if self.times else 0

    @property
    def max_t(self):
        return max(self.times) if self.times else 0

    def _percentile(self, p):
        if not self.times:
            return 0
        sorted_t = sorted(self.times)
        idx = int(len(sorted_t) * p / 100)
        idx = min(idx, len(sorted_t) - 1)
        return sorted_t[idx]

    def row(self):
        return [
            f"{self.method} {self.endpoint}",
            self.count,
            self.errors,
            f"{self.avg * 1000:.1f}",
            f"{self.p50 * 1000:.1f}",
            f"{self.p95 * 1000:.1f}",
            f"{self.p99 * 1000:.1f}",
            f"{self.min_t * 1000:.1f}",
            f"{self.max_t * 1000:.1f}",
        ]


async def authenticate(client: httpx.AsyncClient, base_url: str, email: str, password: str):
    """Login via form POST and capture the auth cookie."""
    resp = await client.post(
        f"{base_url}{PREFIX}/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    if resp.status_code not in (302, 303):
        # Try API login as fallback
        resp = await client.post(
            f"{base_url}{PREFIX}/api/v1/auth/login",
            data={"email": email, "password": password},
        )
        if resp.status_code != 200:
            print(f"ERROR: Login failed with status {resp.status_code}", file=sys.stderr)
            print(f"Response: {resp.text[:500]}", file=sys.stderr)
            sys.exit(1)
        token = resp.json().get("access_token")
        if token:
            client.cookies.set("casehub_token", token)
            print(f"  Authenticated via API login (token cookie set)")
            return
    else:
        print(f"  Authenticated via form login (cookie set by redirect)")


async def run_single(client: httpx.AsyncClient, method: str, url: str, result: BenchmarkResult, **kwargs):
    """Execute a single request and record timing."""
    try:
        start = time.perf_counter()
        resp = await getattr(client, method)(url, follow_redirects=True, **kwargs)
        elapsed = time.perf_counter() - start
        result.times.append(elapsed)
        code = resp.status_code
        result.status_codes[code] = result.status_codes.get(code, 0) + 1
        if code >= 400:
            result.errors += 1
    except Exception as e:
        result.errors += 1


async def run_endpoint(client: httpx.AsyncClient, method: str, url: str, n: int, concurrency: int, label: str = None, **kwargs):
    """Run N requests against an endpoint with bounded concurrency."""
    result = BenchmarkResult(endpoint=label or url.split(PREFIX)[-1], method=method.upper())
    sem = asyncio.Semaphore(concurrency)

    async def bounded():
        async with sem:
            await run_single(client, method, url, result, **kwargs)

    tasks = [bounded() for _ in range(n)]
    await asyncio.gather(*tasks)
    return result


async def main(args):
    base = args.base_url.rstrip("/")
    n = args.n
    conc = args.concurrency

    print(f"CaseHub API Benchmark")
    print(f"  Target:      {base}")
    print(f"  Requests:    {n} per endpoint")
    print(f"  Concurrency: {conc}")
    print()

    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Step 1: Authenticate
        print("[1/8] Authenticating...")
        await authenticate(client, base, args.email, args.password)
        print()

        results = []

        # GET /login (public)
        print("[2/8] Benchmarking GET /login ...")
        r = await run_endpoint(client, "get", f"{base}{PREFIX}/login", n, conc, label="/login")
        results.append(r)

        # GET /dashboard (authenticated)
        print("[3/8] Benchmarking GET /dashboard ...")
        r = await run_endpoint(client, "get", f"{base}{PREFIX}/dashboard", n, conc, label="/dashboard")
        results.append(r)

        # GET /clients (list)
        print("[4/8] Benchmarking GET /clients ...")
        r = await run_endpoint(client, "get", f"{base}{PREFIX}/clients", n, conc, label="/clients")
        results.append(r)

        # GET /cases (list)
        print("[5/8] Benchmarking GET /cases ...")
        r = await run_endpoint(client, "get", f"{base}{PREFIX}/cases", n, conc, label="/cases")
        results.append(r)

        # POST /api/clients (create) — uses a dummy payload
        print("[6/8] Benchmarking POST /api/clients ...")
        create_payload = {
            "first_name": "BenchmarkUser",
            "last_name": "LoadTest",
            "email": f"bench-{int(time.time())}@test.local",
            "phone": "555-0000",
        }
        r = await run_endpoint(
            client, "post", f"{base}{PREFIX}/api/clients",
            min(n, 20), conc,  # limit creates to 20 to avoid flooding DB
            label="/api/clients (create)",
            json=create_payload,
        )
        results.append(r)

        # GET /api/clients/1 (single client)
        print("[7/8] Benchmarking GET /api/clients/1 ...")
        r = await run_endpoint(client, "get", f"{base}{PREFIX}/api/clients/1", n, conc, label="/api/clients/1")
        results.append(r)

        # POST /api/documents/upload (file upload with small dummy file)
        print("[8/8] Benchmarking POST /api/documents/upload ...")
        dummy_content = b"Benchmark test file content - " + b"x" * 1024
        upload_files = {"file": ("benchmark_test.txt", io.BytesIO(dummy_content), "text/plain")}
        r = await run_endpoint(
            client, "post", f"{base}{PREFIX}/api/documents/upload",
            min(n, 20), conc,  # limit uploads to 20
            label="/api/documents/upload",
            files=upload_files,
            data={"client_id": "1"},
        )
        results.append(r)

    # Print results table
    print()
    print("=" * 100)
    print("RESULTS")
    print("=" * 100)
    headers = ["Endpoint", "Reqs", "Errors", "Avg(ms)", "P50(ms)", "P95(ms)", "P99(ms)", "Min(ms)", "Max(ms)"]
    rows = [r.row() for r in results]
    print(tabulate(rows, headers=headers, tablefmt="grid"))
    print()

    # Status code summary
    print("Status Code Summary:")
    for r in results:
        codes_str = ", ".join(f"{k}: {v}" for k, v in sorted(r.status_codes.items()))
        print(f"  {r.method} {r.endpoint}: {codes_str}")


def parse_args():
    parser = argparse.ArgumentParser(description="CaseHub API Benchmark")
    parser.add_argument("--base-url", required=True, help="Base URL (e.g. http://localhost:8001)")
    parser.add_argument("--email", required=True, help="Login email")
    parser.add_argument("--password", required=True, help="Login password")
    parser.add_argument("-n", type=int, default=100, help="Number of requests per endpoint (default: 100)")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent requests (default: 5)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
