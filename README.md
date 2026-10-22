# Gemma Developer Agent Benchmark

A small, reproducible kit for comparing code-agent changes cheaply, so a Kaggle submission slot is only spent on a candidate that has already earned it. It provides a nested ladder of task tiers, a paired comparison tool, and a protocol for using them.

It combines two lanes that answer different questions:

1. **Competition mirror:** the official public development tasks, evaluated with the competition's `swegemma eval` harness. Use this whenever the competition bundle is available. The competition reports 129 development tasks and roughly 120 held-out scoring tasks, so this lane is the closest local proxy for the hosted score.
2. **Independent stress set:** all 500 expert-verified SWE-bench Verified tasks, pinned to a fixed Hugging Face dataset revision, organised into the tiers below. This is a supplementary diagnostic, not a predictor of the Kaggle score.

The repository stores code, task IDs and instructions. It does not redistribute competition files, repository snapshots, test patches or reference fixes. The prompt-only manifest omits `patch`, `test_patch` and test-oracle fields. Get the competition files from Kaggle after accepting its rules yourself.

## Tiers: pay for evidence in steps

Tiers are prefixes of a single ordering of the development split, so each one contains the one below it and earlier results are reusable. The ordering interleaves repositories, so even the smallest tier spans several of them.

| Tier | Tasks | Use it for | Committed list |
| --- | --- | --- | --- |
| `smoke8` | 8 | Does the agent run end to end, produce a patch, and log what you need? Not a quality measurement. | [`tiers/smoke8.ids`](tiers/smoke8.ids) |
| `dev32` | 32 | First look at one change. Catches large regressions; too small to confirm small gains. | [`tiers/dev32.ids`](tiers/dev32.ids) |
| `dev96` | 96 | Mid test: the tier to use before deciding whether a change deserves a full run. | [`tiers/dev96.ids`](tiers/dev96.ids) |
| `dev-all` | 400 | Full development lane (nine repositories). | [`tiers/dev-all.ids`](tiers/dev-all.ids) |
| `holdout` | 100 | Three repositories that never appear in development. Run once, for a final candidate only. | [`tiers/holdout.ids`](tiers/holdout.ids) |

`tiers/tiers.json` records the seed, the manifest SHA-256, and the per-repository counts of every tier. Because the tiers are repository-balanced, a tier is **not** an unbiased estimate of the full-set rate (Django is 58% of the development split but a smaller share of `dev32`). Use them to compare a candidate with a baseline on the *same* tasks, and read `by_repository` in the report; do not quote a tier's resolution rate as a headline score.

## Quick start

Python 3.10+ is recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/build_manifest.py --output data/swebench_verified_prompts.jsonl
python tools/validate_manifest.py data/swebench_verified_prompts.jsonl
python tools/make_tiers.py data/swebench_verified_prompts.jsonl --out tiers --write-manifests data
```

The builder streams the pinned dataset instead of caching its Arrow table; the manifest is about 1.6 MB for all 500 tasks and contains issue prompts, repository names and base commits only. `make_tiers.py` is deterministic: re-running it must reproduce the committed `tiers/*.ids` exactly (`git diff --exit-code tiers` is a good check). `--write-manifests data` also writes `data/tier-<name>.jsonl` for each tier.

The earlier random lane is still available: `python tools/build_manifest.py --split development --limit 32 --seed 20261020 --output data/dev32.jsonl`. It is a different 32 tasks from the balanced `dev32` tier, so do not mix their results.

## Running a tier

Use the **same** task IDs, budgets, hardware and environment for baseline and candidate.

For the competition mirror, pass the IDs to the official harness:

```bash
swegemma eval \
  --tasks /path/to/tasks.jsonl \
  --snapshots-dir /path/to/snapshots \
  --submission-dir /path/to/your/submission \
  --results-dir results/baseline \
  --sandbox docker \
  --task-ids TASK_ID_1 TASK_ID_2 \
  --concurrency 2
```

The competition bundle is large (about 22.42 GB); keep it in Kaggle or another cloud workspace rather than in this repo. Start with 8 to 16 tasks, then use the full public development set.

For the SWE-bench stress set, generate one unified diff per task and run the official evaluator, for example:

```bash
swebench eval verified -p /path/to/predictions.jsonl --run-id gemma-candidate-001 -j 2
```

Flags follow the installed `swebench` release. Full local runs can need roughly 120 GB of free disk, so use a cloud machine and a small worker count. The prompt-only tiers do not replace the task environments the evaluator needs.

## Comparing runs

`swegemma eval` writes `task_results.jsonl` into `--results-dir`. The comparer needs one JSON object per task with at least:

```json
{"instance_id":"owner__repo-123","resolved":true}
```

`task_id` or `id` are accepted in place of `instance_id`. Optional numeric fields `elapsed_seconds` (also `duration_seconds`, `wall_time_seconds`), `total_tokens` (also `tokens`) and `tool_calls` are reported as paired mean changes, but only when every task in both runs has the field. Check the field names in your own harness output; they are not assumed to match.

```bash
python tools/compare_runs.py \
  --baseline results/baseline/task_results.jsonl \
  --candidate results/candidate/task_results.jsonl \
  --bootstrap 10000 --seed 42
```

The report gives both resolution rates, the paired change in percentage points with a paired-bootstrap 95% interval, the improved and regressed task counts with an exact two-sided McNemar (sign test) p-value on those discordant pairs, per-repository results, and cost changes when available. It fails if the runs do not contain the same unique task IDs. `examples/` has a runnable toy pair (four invented tasks; no performance information).

## Protocol

1. Freeze a baseline and run ID. Record model variant, adapter SHA-256, agent config hash, prompt hash, seed, tool and time limits, harness version, task-manifest hash and hardware.
2. Change one thing per candidate. Keep everything else identical.
3. Climb the ladder: `smoke8` for plumbing, `dev32` to drop clear losers, `dev96` to confirm, then the full development lane. Stop climbing as soon as the candidate is clearly not better.
4. Report resolved counts, the paired change and its interval, discordant counts, failures, wall time and tokens if available. Do not select on a small point estimate.
5. Run `holdout` once, for the final candidate only. Do not tune on it.
6. Spend a daily submission slot only after the candidate has passed the local comparison and the official format and runtime checks.

How small a difference you can see is limited by the number of tasks that change outcome, not by the tier size alone. With few discordant pairs the interval will be wide; a clean result on `dev32` is a screening result.

## Limitations

- SWE-bench Verified is public and may overlap model training data. It adds breadth to a 129-task development set but is not more representative of the hidden Kaggle tasks by default.
- A prompt-hygiene audit found 17 of 500 hints (3.4%) with patch-like text. This is not confirmed leakage. See [docs/hint-audit.md](docs/hint-audit.md); `--blank-hints` and [`tiers/hint_patch_signal.ids`](tiers/hint_patch_signal.ids) support a hint-free repeat.
- The competition and SWE-bench harnesses differ. Do not pool scores from the two lanes into one number.
- A passing local suite does not guarantee a hidden task passes. Treat development results as directional.
- This kit does not run Gemma inference. It standardises task selection and paired analysis; use the same agent and model settings you intend to submit.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Sources

- [Gemma 4 Developer Agent competition overview](https://www.kaggle.com/competitions/gemma-4-developer-agent/overview)
- [SWE-bench dataset guide](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/datasets.md)
- [SWE-bench repository and evaluator](https://github.com/SWE-bench/SWE-bench)
- [Pinned SWE-bench Verified dataset revision](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/tree/78f471bf655a3137b2e8a75af1501690ec009ec3)

Part of the research write-up at <https://blessingsmambwe.web.app/gemma4challenge/latest/>.
