import json
import subprocess
import sys
from pathlib import Path

import pytest

from compare_runs import cost_summary, mcnemar_exact_p

ROOT = Path(__file__).resolve().parents[1]


def run_compare(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "compare_runs.py"), *args],
        capture_output=True, text=True,
    )


def test_mcnemar_known_values():
    assert mcnemar_exact_p(0, 0) == 1.0
    assert mcnemar_exact_p(5, 5) == 1.0
    assert mcnemar_exact_p(0, 8) == pytest.approx(2 / 256)
    assert mcnemar_exact_p(3, 1) == pytest.approx(0.625)


def test_cost_summary_requires_complete_fields():
    base = {"a": {"elapsed_seconds": 10}, "b": {"elapsed_seconds": 30}}
    cand = {"a": {"elapsed_seconds": 5}, "b": {"elapsed_seconds": 15}}
    out = cost_summary(base, cand, ["a", "b"])
    assert out["elapsed_seconds"]["change_percent"] == pytest.approx(-50.0)
    assert "total_tokens" not in out
    del cand["b"]["elapsed_seconds"]
    assert cost_summary(base, cand, ["a", "b"]) == {}


def test_cli_on_toy_examples(tmp_path):
    out = tmp_path / "report.json"
    result = run_compare(
        "--baseline", str(ROOT / "examples" / "baseline.jsonl"),
        "--candidate", str(ROOT / "examples" / "candidate.jsonl"),
        "--bootstrap", "200", "--json-out", str(out),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert (report["n"], report["improved_tasks"], report["regressed_tasks"]) == (4, 1, 0)
    assert report["delta_percentage_points"] == 25.0


def test_mismatched_task_sets_fail(tmp_path):
    other = tmp_path / "other.jsonl"
    other.write_text('{"instance_id":"zzz","resolved":true}\n', encoding="utf-8")
    result = run_compare("--baseline", str(ROOT / "examples" / "baseline.jsonl"), "--candidate", str(other))
    assert result.returncode != 0 and "same task IDs" in result.stderr
