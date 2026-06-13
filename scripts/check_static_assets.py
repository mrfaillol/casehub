#!/usr/bin/env python3
"""Verify that public static assets are served with the expected MIME type."""

from __future__ import annotations

import argparse
import ssl
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_CSS_PATHS = [
    "/static/css/themes/_tokens.css",
    "/static/css/themes/glass.css",
    "/static/css/tokens.css",
    "/static/css/reset.css",
    "/static/css/components/buttons.css",
    "/static/css/components/forms.css",
    "/static/css/components/cards.css",
    "/static/css/casehub-browser-basic.css",
    "/static/css/casehub-login-basic.css",
    "/static/brand-kit/tokens.css",
    # Minified assets produced by build:dashboard-assets
    "/static/css/casehub-browser-basic.min.css",
    "/static/css/casehub-login-basic.min.css",
    "/static/css/design-system.min.css",
    "/static/css/liquid-glass.min.css",
    "/static/brand-kit/tokens.min.css",
]


@dataclass
class AssetResult:
    url: str
    status: int
    content_type: str
    ok: bool
    error: str = ""


def normalize_base(base: str) -> str:
    return base.rstrip("/") + "/"


def asset_url(base: str, path: str) -> str:
    return urljoin(normalize_base(base), path.lstrip("/"))


def check_asset(url: str, expected_type: str, timeout: float, insecure: bool = False) -> AssetResult:
    request = Request(url, method="GET", headers={"User-Agent": "casehub-static-smoke/1.0"})
    context = ssl._create_unverified_context() if insecure else None
    try:
        with urlopen(request, timeout=timeout, context=context) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            ok = 200 <= status < 300 and expected_type in content_type.lower()
            return AssetResult(url=url, status=status, content_type=content_type, ok=ok)
    except HTTPError as exc:
        return AssetResult(
            url=url,
            status=exc.code,
            content_type=exc.headers.get("Content-Type", ""),
            ok=False,
            error=str(exc),
        )
    except URLError as exc:
        return AssetResult(url=url, status=0, content_type="", ok=False, error=str(exc.reason))


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        action="append",
        required=True,
        help="Base origin to verify, for example https://casehub.example.com",
    )
    parser.add_argument(
        "--css",
        action="append",
        default=[],
        help="Additional CSS path to verify. Defaults cover the Lite shell.",
    )
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument(
        "--expected-type",
        default="text/css",
        help="Required Content-Type substring for CSS checks. Defaults to text/css.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification for non-production/self-signed environments.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    css_paths = DEFAULT_CSS_PATHS + args.css
    failures: list[AssetResult] = []

    for base in args.base:
        print(f"Static asset smoke: {base}")
        for path in css_paths:
            result = check_asset(asset_url(base, path), args.expected_type, args.timeout, args.insecure)
            label = "OK" if result.ok else "FAIL"
            detail = f"{result.status} {result.content_type or '-'}"
            if result.error:
                detail = f"{detail} {result.error}"
            print(f"  {label:4} {path} -> {detail}")
            if not result.ok:
                failures.append(result)

    if failures:
        print(f"\n{len(failures)} static asset check(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
