#!/usr/bin/env python3
"""Select the next patch version from pack.json and existing release tags."""

import json
from pathlib import Path
import re
import subprocess


VERSION_PATTERN = r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}"


def next_version(version, tags):
    if not isinstance(version, str) or not re.fullmatch(VERSION_PATTERN, version):
        raise ValueError("pack.json version must be MAJOR.MINOR.PATCH")
    versions = [tuple(map(int, version.split(".")))]
    versions.extend(tuple(map(int, tag[1:].split("."))) for tag in tags
                    if re.fullmatch("v" + VERSION_PATTERN, tag))
    major, minor, patch = max(versions)
    return f"{major}.{minor}.{patch + 1}"


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    version = json.loads((root / "pack.json").read_text())["version"]
    tags = subprocess.check_output(["git", "tag", "--list", "v*"], cwd=root, text=True)
    print(next_version(version, tags.splitlines()))
