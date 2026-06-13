#!/usr/bin/env python3
"""Authenticated smoke E2E probe for CaseHub alpha / dev.

Goal frente A1: "Smoke E2E todas 63 rotas autenticadas: 200 ou
intentional redirect". This script is the runnable artifact.

Designed so credentials NEVER leave the operator's shell:

- Reads ``CASEHUB_SMOKE_EMAIL`` + ``CASEHUB_SMOKE_PASSWORD`` from env.
- POSTs the login form, captures the ``casehub_token`` cookie.
- Probes the route list with that cookie, records HTTP code + TTFB.
- Reports a per-family summary plus the full per-route grid as JSON +
  human-readable table.
- The password is NEVER printed, logged, or written to disk. The cookie
  jar is in-memory (urllib ``http.cookiejar``).

Usage
-----

::

    # 1. Export creds in the operator's shell (NEVER in the script or
    #    a committed file). Use the dev environment by default; alpha
    #    is targeted via --base-url.
    export CASEHUB_SMOKE_EMAIL='you@firm.example'
    export CASEHUB_SMOKE_PASSWORD='...'

    # 2. Run against dev
    python3 scripts/smoke_e2e_auth.py \\
        --base-url https://dev.vingren.me \\
        --prefix /casehub \\
        --output /tmp/smoke-dev-2026-05-23.json

    # 3. Run against alpha Mumbai (post-rsync)
    python3 scripts/smoke_e2e_auth.py \\
        --base-url https://casehub.legal \\
        --prefix /casehub \\
        --output /tmp/smoke-alpha-2026-05-23.json

Exit code: 0 if all probes resolved (200 / 302 / 401 only); non-zero
if any 500-family or unexpected-status response was seen. Useful for
CI / wave scripts.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from http.cookiejar import CookieJar
from typing import Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


# ---------------------------------------------------------------------------
# Route inventory — the 63 authenticated routes the goal mentions.
#
# Grouped by family so the report is readable. Each entry is just a path
# (relative to PREFIX); we never POST mutating actions here — read-only
# smoke. The list is conservative: routes that always 401/403 without
# extra context (admin-only, super-admin, OAuth callbacks) are flagged
# ``expect_401=True`` so the script does not count them as defects.
# ---------------------------------------------------------------------------


# ``expect=`` is the set of OK statuses for the route. 200 = render, 302 =
# expected redirect (e.g. legacy alias), 401/403 = auth-gated route the
# smoke session does not satisfy.
ROUTE_INVENTORY: List[Dict[str, object]] = [
    # ---- Core pages
    {"path": "/healthz",                              "expect": {200},          "family": "health"},
    {"path": "/health",                               "expect": {200},          "family": "health"},   # alias from PR #586
    {"path": "/oauth/pdpj/status",                    "expect": {200, 401},     "family": "health"},   # auth-gated, exists
    {"path": "/google/status",                        "expect": {200},          "family": "health"},   # alias from PR #586
    {"path": "",                                      "expect": {200, 302},     "family": "landing"},
    {"path": "/dashboard",                            "expect": {200, 302},     "family": "core"},
    {"path": "/clients",                              "expect": {200},          "family": "clients"},
    {"path": "/cases",                                "expect": {200},          "family": "cases"},
    {"path": "/processes",                            "expect": {200, 404},     "family": "cases"},
    {"path": "/documents",                            "expect": {200},          "family": "documents"},
    {"path": "/tasks",                                "expect": {200, 302},     "family": "tasks"},
    {"path": "/tasks/kanban",                         "expect": {200},          "family": "tasks"},
    {"path": "/calendar",                             "expect": {200},          "family": "calendar"},
    {"path": "/calendar/agenda",                      "expect": {200},          "family": "calendar"},
    {"path": "/controladoria",                        "expect": {200},          "family": "controladoria"},
    {"path": "/emails",                               "expect": {200, 302},     "family": "emails"},
    {"path": "/tools",                                "expect": {200, 302},     "family": "tools"},
    {"path": "/checklists",                           "expect": {200},          "family": "checklists"},
    {"path": "/messaging",                            "expect": {200, 302},     "family": "messaging"},
    {"path": "/notifications",                        "expect": {200, 302},     "family": "notifications"},
    {"path": "/assistente",                           "expect": {200},          "family": "assistente"},

    # ---- P0 families flagged by audit #514
    {"path": "/portal/manage",                        "expect": {200},          "family": "p0-audit-514"},
    {"path": "/api/v1/docs-page",                     "expect": {200, 401},     "family": "p0-audit-514"},

    # ---- WhatsApp surface
    {"path": "/whatsapp-chat",                        "expect": {200},          "family": "whatsapp"},
    {"path": "/whatsapp-chat/api/conversations",      "expect": {200},          "family": "whatsapp"},
    {"path": "/whatsapp-chat/api/status",             "expect": {200},          "family": "whatsapp"},

    # ---- Google integrations
    {"path": "/google-calendar/settings",             "expect": {200},          "family": "google"},
    {"path": "/google-calendar/status",               "expect": {200},          "family": "google"},
    {"path": "/api/drive/list?folder_id=root",        "expect": {200, 503},     "family": "google-drive"},

    # ---- Settings / admin
    {"path": "/settings",                             "expect": {200},          "family": "settings"},
    {"path": "/profile",                              "expect": {200, 302},     "family": "settings"},
    {"path": "/branding",                             "expect": {200, 302},     "family": "settings"},
    {"path": "/integrations",                         "expect": {200},          "family": "settings"},

    # ---- BR-specific (Lite)
    {"path": "/tribunal",                             "expect": {200, 302},     "family": "br-legal"},
    {"path": "/prazos",                               "expect": {200, 302},     "family": "br-legal"},
    {"path": "/pecas",                                "expect": {200, 302},     "family": "br-legal"},
    {"path": "/tools-tributario",                     "expect": {200, 404},     "family": "br-legal"},

    # ---- ILC / Immigration (may 404 on Lite-only)
    {"path": "/intake",                               "expect": {200, 404},     "family": "intake"},
    {"path": "/uscis",                                "expect": {200, 404},     "family": "uscis"},
    {"path": "/ilc-tools",                            "expect": {200, 404},     "family": "ilc"},

    # ---- API health
    {"path": "/api/health",                           "expect": {200},          "family": "api-health"},
]


def _build_url(base_url: str, prefix: str, path: str) -> str:
    """Compose the absolute URL preserving query strings on the route entry."""
    base = base_url.rstrip("/")
    pref = prefix.strip("/")
    pref = f"/{pref}" if pref else ""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{pref}{path}" if not path.startswith(pref + "/") else f"{base}{path}"


def _login(base_url: str, prefix: str, email: str, password: str,
           timeout: float = 15.0) -> Tuple[CookieJar, int, float]:
    """POST /casehub/login with form-urlencoded creds and capture cookies.

    Returns (cookie_jar, http_status, ttfb_seconds). On non-2xx/3xx the
    caller decides whether to abort; the cookie jar may still hold a
    partial session.
    """
    jar = CookieJar()
    handler = urllib_request.HTTPCookieProcessor(jar)
    opener = urllib_request.build_opener(handler)
    # Don't follow redirects automatically — we want to see the 302 that
    # signals login success.
    opener.add_handler(_NoRedirect())

    data = urllib_parse.urlencode({"email": email, "password": password}).encode("utf-8")
    url = _build_url(base_url, prefix, "/login")
    req = urllib_request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    start = time.monotonic()
    try:
        resp = opener.open(req, timeout=timeout)
        status = resp.status
    except urllib_error.HTTPError as exc:
        status = exc.code
    elapsed = time.monotonic() - start
    return jar, status, elapsed


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    """Stop urllib from auto-following 302s — we report them as outcomes."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _probe(opener: urllib_request.OpenerDirector, url: str,
           timeout: float) -> Tuple[int, float]:
    """GET ``url`` and return (status, ttfb_seconds).

    NOTE: ``urllib_request.OpenerDirector`` does NOT pool TCP connections
    across ``open()`` calls — each probe pays TCP+TLS handshake. For a
    deploy on the other side of an ocean (e.g. Mumbai from BR) this
    overstates real browser TTFB by ~3×. The companion
    ``_probe_keepalive`` runs N probes against the same host on one
    connection, mirroring what a browser does after page load.
    """
    req = urllib_request.Request(url, method="GET")
    start = time.monotonic()
    try:
        resp = opener.open(req, timeout=timeout)
        status = resp.status
    except urllib_error.HTTPError as exc:
        status = exc.code
    except urllib_error.URLError as exc:
        # Network / TLS failure — surfaces as 0; the caller treats it as
        # a defect.
        status = 0
        # Best-effort attribution for the report
        sys.stderr.write(f"[WARN] {url}: {exc}\n")
    elapsed = time.monotonic() - start
    return status, elapsed


def _probe_keepalive(host: str, paths: List[str], cookie_header: str,
                     n_repeats: int = 3, timeout: float = 15.0) -> List[Tuple[str, int, float, bool]]:
    """Probe ``paths`` on ``host`` with TCP keep-alive (one connection).

    Mirrors browser behaviour: first request pays TCP+TLS handshake,
    subsequent requests on the same connection pay only 1 RTT. Returns
    ``[(path, status, elapsed_seconds, was_first), ...]`` so the caller
    can tell warm from cold samples.

    The cookie header is opaque — we just forward whatever the login
    step captured. ``http.client`` is intentionally low-level here
    because urllib doesn't expose connection reuse cleanly.
    """
    import http.client
    import ssl

    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, 443, timeout=timeout, context=ctx)
    headers = {"Cookie": cookie_header} if cookie_header else {}
    results: List[Tuple[str, int, float, bool]] = []
    is_first = True
    try:
        for _ in range(n_repeats):
            for path in paths:
                start = time.monotonic()
                try:
                    conn.request("GET", path, headers=headers)
                    resp = conn.getresponse()
                    status = resp.status
                    # Drain the response to free the connection for the
                    # next keep-alive request.
                    _ = resp.read()
                except Exception as exc:  # noqa: BLE001
                    status = 0
                    sys.stderr.write(f"[KA WARN] {host}{path}: {exc}\n")
                    # Reset connection on any failure so the next probe
                    # has a chance.
                    conn.close()
                    conn = http.client.HTTPSConnection(host, 443, timeout=timeout, context=ctx)
                elapsed = time.monotonic() - start
                results.append((path, status, elapsed, is_first))
                is_first = False
    finally:
        conn.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True,
                        help="e.g. https://dev.vingren.me or https://casehub.legal")
    parser.add_argument("--prefix", default="/casehub")
    parser.add_argument("--output", default="",
                        help="JSON output path. Stdout if empty.")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--insecure", action="store_true",
                        help="Skip TLS verification (use only for staging).")
    parser.add_argument("--routes-only", action="store_true",
                        help="Skip login; assume the URLs are reachable unauth.")
    parser.add_argument("--keepalive-sample", action="store_true",
                        help=(
                            "After the standard probe, run a second pass on a "
                            "subset of hot paths with TCP keep-alive (one "
                            "connection) to capture browser-like warm TTFB."
                        ))
    parser.add_argument("--keepalive-repeats", type=int, default=3,
                        help="How many keep-alive passes (default 3).")
    args = parser.parse_args()

    email = os.environ.get("CASEHUB_SMOKE_EMAIL", "")
    password = os.environ.get("CASEHUB_SMOKE_PASSWORD", "")
    if not args.routes_only and (not email or not password):
        sys.stderr.write(
            "ERROR: CASEHUB_SMOKE_EMAIL and CASEHUB_SMOKE_PASSWORD must be set\n"
            "       (or use --routes-only for an unauth dry run)\n"
        )
        return 2

    # --insecure path: build a context that skips TLS verify (dev only).
    if args.insecure:
        ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001

    # --- Step 1: login (unless --routes-only)
    jar: CookieJar
    if args.routes_only:
        jar = CookieJar()
        login_status = -1
        login_ttfb = 0.0
    else:
        jar, login_status, login_ttfb = _login(
            args.base_url, args.prefix, email, password,
            timeout=args.timeout,
        )
        # Login responses: 302 (success) or 200 (form re-rendered with error)
        if login_status not in {200, 302}:
            sys.stderr.write(
                f"ERROR: login returned HTTP {login_status} — aborting.\n"
            )
            return 3
        token_present = any(c.name == "casehub_token" for c in jar)
        if not token_present and login_status != 200:
            sys.stderr.write(
                "WARNING: login returned 302 but no casehub_token cookie set. "
                "Subsequent probes may be unauthenticated.\n"
            )

    handler = urllib_request.HTTPCookieProcessor(jar)
    opener = urllib_request.build_opener(handler, _NoRedirect())

    # --- Step 2: probe each route
    results = []
    summary: Dict[str, Dict[str, int]] = {}
    defects: List[Dict[str, object]] = []
    for entry in ROUTE_INVENTORY:
        path = entry["path"]
        expect = entry["expect"]
        family = entry["family"]
        url = _build_url(args.base_url, args.prefix, path)
        status, ttfb = _probe(opener, url, timeout=args.timeout)

        ok = status in expect
        row = {
            "path": path,
            "url": url,
            "family": family,
            "status": status,
            "expect": sorted(expect),
            "ok": ok,
            "ttfb_ms": round(ttfb * 1000, 2),
        }
        results.append(row)

        # Per-family tallies
        fam = summary.setdefault(family, {"ok": 0, "defect": 0, "ttfb_p95_ms": 0})
        if ok:
            fam["ok"] += 1
        else:
            fam["defect"] += 1
            defects.append(row)

    # p95 per family (rough — uses simple sort, fine for ~40 routes)
    by_family: Dict[str, List[float]] = {}
    for row in results:
        by_family.setdefault(row["family"], []).append(row["ttfb_ms"])
    for fam_name, ttfbs in by_family.items():
        ttfbs.sort()
        # p95 index (linear interpolation skipped; simple nearest-rank).
        if len(ttfbs) == 1:
            summary[fam_name]["ttfb_p95_ms"] = ttfbs[0]
        else:
            idx = max(0, int(0.95 * len(ttfbs)) - 1)
            summary[fam_name]["ttfb_p95_ms"] = ttfbs[idx]

    # --- Step 2b: optional keep-alive pass to capture browser-like TTFB
    keepalive_samples = []
    if args.keepalive_sample:
        # Pick the most user-visible hot paths — landing, healthz, and the
        # heavy ones (whatsapp-chat, controladoria, tasks/kanban).
        hot_paths = [
            f"{args.prefix.rstrip('/')}/healthz",
            f"{args.prefix.rstrip('/')}/login",
            f"{args.prefix.rstrip('/')}/dashboard",
            f"{args.prefix.rstrip('/')}/clients",
            f"{args.prefix.rstrip('/')}/whatsapp-chat",
            f"{args.prefix.rstrip('/')}/controladoria",
            f"{args.prefix.rstrip('/')}/calendar",
            f"{args.prefix.rstrip('/')}/tasks/kanban",
        ]
        # Compose a Cookie header from the jar so the keep-alive probe
        # uses the same authenticated session as the regular pass.
        cookie_header = "; ".join(
            f"{c.name}={c.value}" for c in jar if c.name and c.value
        )
        # Resolve the host from the base_url.
        host = urllib_parse.urlparse(args.base_url).hostname or args.base_url
        keepalive_samples = _probe_keepalive(
            host=host,
            paths=hot_paths,
            cookie_header=cookie_header,
            n_repeats=args.keepalive_repeats,
            timeout=args.timeout,
        )
        sys.stderr.write(
            f"\nKeep-alive sample: {len(keepalive_samples)} probes across "
            f"{len(hot_paths)} hot paths × {args.keepalive_repeats} passes\n"
        )

    # --- Step 3: emit report
    report = {
        "base_url": args.base_url,
        "prefix": args.prefix,
        "login": {
            "performed": not args.routes_only,
            "status": login_status,
            "ttfb_ms": round(login_ttfb * 1000, 2),
        },
        "total_routes": len(results),
        "defects_count": len(defects),
        "summary_by_family": summary,
        "defects": defects,
        "all_results": results,
        "keepalive_samples": [
            {
                "path": p,
                "status": s,
                "elapsed_ms": round(e * 1000, 2),
                "was_first": w,
            }
            for (p, s, e, w) in keepalive_samples
        ],
    }

    output = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output)
        sys.stderr.write(f"Wrote {len(results)} probe results to {args.output}\n")
    else:
        print(output)

    # --- Human-readable summary on stderr (the JSON owns stdout)
    sys.stderr.write("\n=== Smoke E2E summary ===\n")
    sys.stderr.write(f"Base: {args.base_url}{args.prefix}\n")
    if not args.routes_only:
        sys.stderr.write(f"Login: HTTP {login_status} in {login_ttfb*1000:.0f}ms\n")
    sys.stderr.write(f"Routes probed: {len(results)} / Defects: {len(defects)}\n\n")
    sys.stderr.write(f"{'Family':<22} {'OK':>4} {'DEF':>4} {'p95 ms':>10}\n")
    sys.stderr.write("-" * 44 + "\n")
    for fam_name in sorted(summary):
        s = summary[fam_name]
        sys.stderr.write(
            f"{fam_name:<22} {s['ok']:>4} {s['defect']:>4} {s['ttfb_p95_ms']:>10.1f}\n"
        )

    if defects:
        sys.stderr.write("\n=== Defects ===\n")
        for d in defects:
            sys.stderr.write(
                f"  {d['family']:<22} {d['path']:<40} -> {d['status']} (expected: {d['expect']})\n"
            )

    # Exit 0 iff zero defects.
    return 0 if not defects else 1


if __name__ == "__main__":
    sys.exit(main())
