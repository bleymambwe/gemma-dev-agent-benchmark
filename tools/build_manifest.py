#!/usr/bin/env python3
"""Build a prompt-only SWE-bench Verified manifest from its pinned HF revision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DATASET = "SWE-bench/SWE-bench_Verified"
REVISION = "78f471bf655a3137b2e8a75af1501690ec009ec3"
KEEP_FIELDS = ("instance_id", "repo", "base_commit", "problem_statement", "hints_text", "version")


def split_repositories(rows: list[dict[str, Any]], seed: int, holdout_fraction: float) -> dict[str, str]:
    """Assign whole repositories to a deterministic holdout, avoiding repo leakage."""
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["repo"]] = counts.get(row["repo"], 0) + 1
    repos = sorted(counts, key=lambda repo: hashlib.sha256(f"{seed}:{repo}".encode()).hexdigest())
    if len(repos) < 2:
        raise ValueError("At least two repositories are needed for a repository-held-out split")

    target = round(len(rows) * holdout_fraction)
    # Find the closest whole-repository subset to the requested target. Hash order
    # makes ties reproducible without allowing large repos to skew a greedy split.
    choices: dict[int, tuple[str, ...]] = {0: ()}
    for repo in repos:
        for size, chosen in list(choices.items()):
            new_size = size + counts[repo]
            candidate = chosen + (repo,)
            if new_size not in choices or len(candidate) < len(choices[new_size]):
                choices[new_size] = candidate
    candidates = [
        (size, chosen)
        for size, chosen in choices.items()
        if 0 < size < len(rows) and chosen
    ]
    if not candidates:
        raise ValueError("Could not form non-empty development and holdout repository splits")
    _, chosen = min(
        candidates,
        key=lambda item: (
            abs(item[0] - target),
            item[0] > target,
            tuple(repos.index(repo) for repo in item[1]),
        ),
    )
    holdout = set(chosen)
    return {repo: ("holdout" if repo in holdout else "development") for repo in repos}


def build_rows(seed: int, holdout_fraction: float) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("Install dependencies first: python -m pip install -r requirements.txt") from exc

    dataset = load_dataset(DATASET, split="test", revision=REVISION)
    rows: list[dict[str, Any]] = []
    for source in dataset:
        row = {key: source.get(key) for key in KEEP_FIELDS}
        row["hints_text"] = row["hints_text"] or ""
        rows.append(row)
    if len(rows) != 500:
        raise ValueError(f"Expected 500 pinned examples; received {len(rows)}")
    if len({row["instance_id"] for row in rows}) != len(rows):
        raise ValueError("The pinned dataset contains duplicate instance IDs")

    split_map = split_repositories(rows, seed, holdout_fraction)
    for row in rows:
        row["split"] = split_map[row["repo"]]
        row["source_dataset"] = DATASET
        row["source_revision"] = REVISION
    return sorted(rows, key=lambda row: row["instance_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    parser.add_argument("--split", choices=("all", "development", "holdout"), default="all")
    parser.add_argument("--limit", type=int, help="Keep a stable, ID-sorted prefix after filtering")
    args = parser.parse_args()
    if not 0.05 <= args.holdout_fraction <= 0.5:
        parser.error("--holdout-fraction must be between 0.05 and 0.5")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    rows = build_rows(args.seed, args.holdout_fraction)
    if args.split != "all":
        rows = [row for row in rows if row["split"] == args.split]
    if args.limit is not None:
        rows = sorted(
            rows,
            key=lambda row: hashlib.sha256(f"{args.seed}:{row['instance_id']}".encode()).hexdigest(),
        )[: args.limit]
        rows.sort(key=lambda row: row["instance_id"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    dev = sum(row["split"] == "development" for row in rows)
    holdout = sum(row["split"] == "holdout" for row in rows)
    print(f"Wrote {len(rows)} prompt-only tasks to {args.output} (development={dev}, holdout={holdout})")
    print("Oracle patches and test patches were excluded.")


if __name__ == "__main__":
    main()
