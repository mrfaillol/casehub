#!/usr/bin/env python3
"""
Lightweight PR guard for CaseHub Performance Guardian.

This is intentionally cheap: it checks only changed files and rejects obvious
performance/red-line regressions. Full route benchmarks run in the Oracle dev
nightly lane.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


BLOCKED_PATH_PATTERNS = [
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"(^|/)credentials/"),
    re.compile(r"(^|/)secrets/"),
    re.compile(r"\.(pem|key|p12|pfx|jks|keystore)$"),
    re.compile(r"docs/security/deploy-halt\.json$"),
]

TEXT_EXTENSIONS = {".css", ".js", ".mjs", ".html", ".jinja", ".jinja2", ".py", ".md", ".yml", ".yaml"}
MAX_CHANGED_TEXT_FILE_BYTES = 2_500_000
MAX_NEW_BACKDROP_FILTERS = 12
PUBLIC_ENV_EXAMPLE_FILES = {".env.example"}
GENERATED_CSS_BUDGET_EXEMPTIONS = {"static/css/app/index.bundle.css"}


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()


def changed_files(base_ref: str) -> list[str]:
    candidates = [
        ["diff", "--name-only", f"{base_ref}...HEAD"],
        ["diff", "--cached", "--name-only"],
        ["diff", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
        ["diff", "--name-only", "HEAD~1...HEAD"],
    ]
    for command in candidates:
        try:
            output = run_git(command)
            files = [line for line in output.splitlines() if line]
            if files:
                return files
        except Exception:
            continue
    return []


def check_paths(paths: list[str]) -> list[str]:
    failures = []
    for path in paths:
        if Path(path).name in PUBLIC_ENV_EXAMPLE_FILES:
            continue
        for pattern in BLOCKED_PATH_PATTERNS:
            if pattern.search(path):
                failures.append(f"{path}: blocked path for Performance Guardian")
    return failures


def count_backdrop_filters(content: str) -> int:
    return content.count("backdrop-filter") + content.count("-webkit-backdrop-filter")


def base_file_content(base_ref: str, path: str) -> str:
    try:
        return run_git(["show", f"{base_ref}:{path}"])
    except Exception:
        return ""


def check_file_budgets(paths: list[str], base_ref: str) -> list[str]:
    failures = []
    for path_text in paths:
        if path_text in GENERATED_CSS_BUDGET_EXEMPTIONS:
            continue
        path = Path(path_text)
        if not path.exists() or path.suffix not in TEXT_EXTENSIONS:
            continue
        size = path.stat().st_size
        if size > MAX_CHANGED_TEXT_FILE_BYTES:
            failures.append(f"{path}: changed text file is {size} bytes > {MAX_CHANGED_TEXT_FILE_BYTES}")
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix == ".css" and "static/css/desktop/" not in path_text:
            current_count = count_backdrop_filters(content)
            base_count = count_backdrop_filters(base_file_content(base_ref, path_text))
            added_count = max(0, current_count - base_count)
            if added_count > MAX_NEW_BACKDROP_FILTERS:
                failures.append(
                    f"{path}: {added_count} new backdrop-filter declarations > {MAX_NEW_BACKDROP_FILTERS} "
                    f"(current={current_count}, base={base_count})"
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default=os.getenv("BASE_REF", "origin/main"))
    args = parser.parse_args(argv)

    paths = changed_files(args.base_ref)
    failures = check_paths(paths) + check_file_budgets(paths, args.base_ref)
    print(f"Performance Guardian static check: {len(paths)} changed file(s)")
    if failures:
        for failure in failures:
            print(f"::error::{failure}")
        return 1
    print("OK: static performance/red-line check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
