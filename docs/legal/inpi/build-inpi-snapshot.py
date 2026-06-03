#!/usr/bin/env python3
"""Build a deterministic CaseHub Basic source snapshot for INPI evidence."""

from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path


INCLUDE_PATHS = [
    "app.py",
    "auth.py",
    "config.py",
    "i18n.py",
    "core",
    "migrations",
    "middleware",
    "models",
    "routes",
    "static",
    "templates",
    "products",
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "requirements-lite.txt",
    "pytest.ini",
    "Dockerfile",
    "Dockerfile.lite",
    "Makefile",
    "VERSION_COMMIT",
    "README.md",
]

EXCLUDED_PREFIXES = (
    "templates/_archive/",
    "static/reports/",
    "services/",
    "scripts/",
    "docs/",
    "test-results/",
    "reports/",
    "uploads/",
    "backups/",
)

EXCLUDED_SUFFIXES = (
    ".docx",
    ".pdf",
    ".bak",
    "~",
)


def git_output(args: list[str]) -> bytes:
    return subprocess.check_output(["git", *args])


def iter_snapshot_paths(commit: str) -> list[str]:
    raw = git_output(["ls-tree", "-rz", "--name-only", commit, "--", *INCLUDE_PATHS])
    paths = [p.decode("utf-8") for p in raw.split(b"\0") if p]
    return sorted(path for path in paths if include_path(path))


def include_path(path: str) -> bool:
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    if path.endswith(EXCLUDED_SUFFIXES):
        return False
    if ".SAFE_BACKUP" in path:
        return False
    return True


def blob_at(commit: str, path: str) -> bytes:
    return git_output(["show", f"{commit}:{path}"])


def write_zip(commit: str, output: Path) -> int:
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    paths = iter_snapshot_paths(commit)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in paths:
            info = zipfile.ZipInfo(path)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, blob_at(commit, path))
    output.chmod(0o600)
    return len(paths)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    count = write_zip(args.commit, args.output)
    print(f"wrote {args.output} with {count} files")


if __name__ == "__main__":
    main()
