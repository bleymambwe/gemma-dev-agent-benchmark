#!/usr/bin/env python3
"""Derive nested, repository-balanced cost tiers from a prompt-only manifest.

Tiers are prefixes of one fixed ordering of the development split, so every
smaller tier is contained in the next one and results can be reused upward:

    smoke8  <  dev32  <  dev96  <  dev-all        (holdout is separate)

The ordering interleaves repositories (one task per repository per pass, each
repository's tasks in seeded hash order). A plain random prefix of a Django-heavy
set is mostly Django; interleaving gives a small tier several repositories.

    python tools/make_tiers.py data/swebench_verified_prompts.jsonl --out tiers
    python tools/make_tiers.py data/swebench_verified_prompts.jsonl --out tiers --write-manifests data
    python tools/make_tiers.py data/swebench_verified_prompts.jsonl --out tiers --write-manifests data --blank-hints
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

TIER_SIZES = {"smoke8": 8, "dev32": 32, "dev96": 96}


def _key(seed: int, text: str) -> str:
    return hashlib.sha256(f"{seed}:{text}".encode()).hexdigest()


def balanced_order(rows: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """Round-robin over repositories; stable for a fixed seed and row set."""
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_repo.setdefault(row["repo"], []).append(row)
    for repo_rows in by_repo.values():
        repo_rows.sort(key=lambda row: _key(seed, row["instance_id"]))
    repos = sorted(by_repo, key=lambda repo: _key(seed, repo))
    ordered: list[dict[str, Any]] = []
    depth = 0
    while len(ordered) < len(rows):
        for repo in repos:
            if depth < len(by_repo[repo]):
                ordered.append(by_repo[repo][depth])
        depth += 1
    return ordered


def build_tiers(rows: list[dict[str, Any]], seed: int) -> dict[str, list[dict[str, Any]]]:
    development = [row for row in rows if row["split"] == "development"]
    holdout = [row for row in rows if row["split"] == "holdout"]
    if len(development) < max(TIER_SIZES.values()):
        raise ValueError(f"Need at least {max(TIER_SIZES.values())} development tasks; found {len(development)}")
    ordered = balanced_order(development, seed)
    tiers: dict[str, list[dict[str, Any]]] = {name: ordered[:size] for name, size in TIER_SIZES.items()}
    tiers["dev-all"] = ordered
    tiers["holdout"] = balanced_order(holdout, seed)
    return tiers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path, help="Full prompt-only manifest from build_manifest.py")
    parser.add_argument("--out", type=Path, default=Path("tiers"), help="Directory for the committed ID lists")
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--write-manifests", type=Path, metavar="DIR", help="Also write tier-<name>.jsonl manifests here")
    parser.add_argument("--blank-hints", action="store_true", help="Empty hints_text in written manifests (hint-free ablation)")
    args = parser.parse_args()

    raw = args.manifest.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    tiers = build_tiers(rows, args.seed)

    args.out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "seed": args.seed,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "source_dataset": rows[0].get("source_dataset"),
        "source_revision": rows[0].get("source_revision"),
        "tiers": {},
    }
    for name, tier_rows in tiers.items():
        ids = [row["instance_id"] for row in tier_rows]
        (args.out / f"{name}.ids").write_text("\n".join(sorted(ids)) + "\n", encoding="utf-8", newline="\n")
        summary["tiers"][name] = {
            "tasks": len(ids),
            "repositories": dict(sorted(Counter(row["repo"] for row in tier_rows).items())),
        }
        if args.write_manifests:
            args.write_manifests.mkdir(parents=True, exist_ok=True)
            with (args.write_manifests / f"tier-{name}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
                for row in sorted(tier_rows, key=lambda r: r["instance_id"]):
                    if args.blank_hints:
                        row = {**row, "hints_text": ""}
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (args.out / "tiers.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name, info in summary["tiers"].items():
        print(f"{name:8s} {info['tasks']:4d} tasks, {len(info['repositories'])} repositories")


if __name__ == "__main__":
    main()
