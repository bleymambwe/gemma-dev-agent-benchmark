#!/usr/bin/env python3
"""Check manifest provenance, split integrity, uniqueness, and oracle exclusion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_manifest import DATASET, REVISION


ORACLE_FIELDS = {"patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS", "eval_script"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        parser.error("manifest is empty")
    ids = [row.get("instance_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in ids):
        parser.error("every row must have a non-empty instance_id")
    if len(set(ids)) != len(ids):
        parser.error("manifest contains duplicate instance_id values")
    for row in rows:
        if row.get("source_dataset") != DATASET or row.get("source_revision") != REVISION:
            parser.error(f"unexpected source provenance in {row.get('instance_id')}")
        if ORACLE_FIELDS.intersection(row):
            parser.error(f"oracle/test fields leaked into {row['instance_id']}")
        if row.get("split") not in {"development", "holdout"}:
            parser.error(f"unknown split in {row['instance_id']}")
    repo_split: dict[str, str] = {}
    for row in rows:
        repo = row.get("repo")
        split = row["split"]
        if not isinstance(repo, str) or not repo:
            parser.error(f"missing repo in {row['instance_id']}")
        if repo in repo_split and repo_split[repo] != split:
            parser.error(f"repository appears in both splits: {repo}")
        repo_split[repo] = split
    print(
        f"Valid: {len(rows)} unique prompt-only tasks; "
        f"development={sum(row['split'] == 'development' for row in rows)}, "
        f"holdout={sum(row['split'] == 'holdout' for row in rows)}, "
        f"repositories={len(repo_split)}"
    )


if __name__ == "__main__":
    main()
