#!/usr/bin/env python3
"""Paired comparison of two per-task binary resolution JSONL result files."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any


def load_results(path: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            instance_id = row.get("instance_id") or row.get("task_id") or row.get("id")
            if not isinstance(instance_id, str) or not instance_id:
                raise ValueError(f"{path}:{line_number}: missing instance_id/task_id/id")
            if instance_id in results:
                raise ValueError(f"{path}:{line_number}: duplicate task {instance_id}")
            resolved = row.get("resolved")
            if not isinstance(resolved, bool):
                raise ValueError(f"{path}:{line_number}: resolved must be true or false")
            results[instance_id] = row
    if not results:
        raise ValueError(f"No results in {path}")
    return results


def bootstrap_interval(deltas: list[int], iterations: int, seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(deltas)
    estimates = sorted(sum(rng.choices(deltas, k=n)) / n for _ in range(iterations))
    return estimates[int(0.025 * iterations)], estimates[min(iterations - 1, int(0.975 * iterations))]


# Optional per-task cost fields, first match wins. Only reported when every task in
# both runs has a numeric value, so a partial log never produces a misleading mean.
COST_FIELDS = {
    "elapsed_seconds": ("elapsed_seconds", "duration_seconds", "wall_time_seconds"),
    "total_tokens": ("total_tokens", "tokens"),
    "tool_calls": ("tool_calls", "num_tool_calls"),
}


def mcnemar_exact_p(improved: int, regressed: int) -> float:
    """Two-sided exact binomial (sign) test on the discordant pairs."""
    n = improved + regressed
    if n == 0:
        return 1.0
    k = min(improved, regressed)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def cost_summary(baseline: dict[str, dict[str, Any]], candidate: dict[str, dict[str, Any]], ids: list[str]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for label, names in COST_FIELDS.items():
        def pick(row: dict[str, Any]) -> float | None:
            for name in names:
                value = row.get(name)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return float(value)
            return None

        pairs = [(pick(baseline[key]), pick(candidate[key])) for key in ids]
        if any(a is None or b is None for a, b in pairs):
            continue
        base_mean = sum(a for a, _ in pairs) / len(pairs)
        cand_mean = sum(b for _, b in pairs) / len(pairs)
        report[label] = {
            "baseline_mean": base_mean,
            "candidate_mean": cand_mean,
            "change_percent": (100 * (cand_mean - base_mean) / base_mean) if base_mean else None,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.bootstrap < 100:
        parser.error("--bootstrap must be at least 100")

    try:
        baseline = load_results(args.baseline)
        candidate = load_results(args.candidate)
        if baseline.keys() != candidate.keys():
            missing_candidate = sorted(baseline.keys() - candidate.keys())
            missing_baseline = sorted(candidate.keys() - baseline.keys())
            raise ValueError(
                "Runs must contain the same task IDs. "
                f"Missing from candidate: {missing_candidate[:5]}; "
                f"missing from baseline: {missing_baseline[:5]}"
            )
    except ValueError as exc:
        parser.error(str(exc))

    ids = sorted(baseline)
    deltas = [int(candidate[key]["resolved"]) - int(baseline[key]["resolved"]) for key in ids]
    base_rate = sum(int(baseline[key]["resolved"]) for key in ids) / len(ids)
    candidate_rate = sum(int(candidate[key]["resolved"]) for key in ids) / len(ids)
    low, high = bootstrap_interval(deltas, args.bootstrap, args.seed)
    improved = sum(delta == 1 for delta in deltas)
    regressed = sum(delta == -1 for delta in deltas)
    report = {
        "n": len(ids),
        "baseline_resolved": round(base_rate * len(ids)),
        "baseline_rate": base_rate,
        "candidate_resolved": round(candidate_rate * len(ids)),
        "candidate_rate": candidate_rate,
        "delta_percentage_points": 100 * (candidate_rate - base_rate),
        "paired_bootstrap_95_percent_interval_percentage_points": [100 * low, 100 * high],
        "improved_tasks": improved,
        "regressed_tasks": regressed,
        "unchanged_tasks": len(ids) - improved - regressed,
        "mcnemar_exact_p_two_sided": mcnemar_exact_p(improved, regressed),
        "bootstrap_iterations": args.bootstrap,
        "seed": args.seed,
    }
    costs = cost_summary(baseline, candidate, ids)
    if costs:
        report["cost"] = costs
    repositories: dict[str, list[str]] = {}
    for instance_id in ids:
        repo = candidate[instance_id].get("repo") or baseline[instance_id].get("repo")
        if isinstance(repo, str) and repo:
            repositories.setdefault(repo, []).append(instance_id)
    if repositories:
        report["by_repository"] = {}
        for repo, repo_ids in sorted(repositories.items()):
            repo_base = sum(int(baseline[key]["resolved"]) for key in repo_ids)
            repo_candidate = sum(int(candidate[key]["resolved"]) for key in repo_ids)
            report["by_repository"][repo] = {
                "n": len(repo_ids),
                "baseline_resolved": repo_base,
                "candidate_resolved": repo_candidate,
                "delta_percentage_points": 100 * (repo_candidate - repo_base) / len(repo_ids),
            }
    print(json.dumps(report, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
