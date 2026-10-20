# Gemma Developer Agent Benchmark

A small, reproducible benchmark kit for comparing code agent changes without spending a Kaggle submission slot. It combines two lanes that answer different questions:

1. **Competition mirror:** the official public development tasks, evaluated with the competition's `swegemma eval` harness. Use this first when the competition bundle is available. The competition reports 129 development tasks and roughly 120 held-out scoring tasks. This lane is the closest local proxy for the hosted score.
2. **Independent stress set:** all 500 expert-verified SWE-bench Verified tasks, pinned to a fixed Hugging Face dataset revision. The kit downloads only issue metadata for prompts; repositories and test environments are managed by the official SWE-bench harness when a run is performed. This is about four times the competition's public development task count, but it is a supplementary diagnostic, not a predictor of the Kaggle score.

This repository stores code, a schema, and run instructions. It does not redistribute competition files, repository snapshots, test patches, or reference fixes. The prompt-only manifest deliberately omits `patch`, `test_patch`, and test-oracle fields. Get the competition files from Kaggle after accepting its rules yourself.

## Quick start

Python 3.10+ is recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/build_manifest.py --output data/swebench_verified_prompts.jsonl
python tools/validate_manifest.py data/swebench_verified_prompts.jsonl
```

The generated manifest is small. It contains 500 issue prompts, repository names, and base commits; it does not include solution patches or tests. To make a stable quick slice for early iteration:

```bash
python tools/build_manifest.py --split development --limit 32 --seed 20261020 --output data/dev32.jsonl
```

Use the **same** task IDs for baseline and candidate runs. Do not tune on the holdout. A deterministic repository-level `split` field labels development and holdout tasks, so no repository appears in both. `--limit` selects a stable subset from the chosen split.

## Evaluating the competition submission

For the closest simulation, use the official competition bundle and the `swegemma` package version documented by the competition. The competition harness guide documents this pattern:

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

Repeat with the exact same task IDs, budgets, hardware, and environment for the candidate. The full competition bundle is large (about 22.42 GB); keep it in Kaggle or another cloud workspace and point the harness to it there. Do not copy it into this repo. Start with 8–16 tasks, then use the full 129 public development tasks for a more stable comparison. Follow the competition terms for access and local evaluation.

## Evaluating the independent SWE-bench supplement

Use a compatible agent to generate one unified diff per task, then run the official SWE-bench evaluator against its frozen task environments. Current SWE-bench CLI usage is documented upstream; for example:

```bash
swebench eval verified \
  -p /path/to/predictions.jsonl \
  --run-id gemma-candidate-001 \
  -j 2
```

The prediction file and exact CLI flags should follow the installed `swebench` release. Full local SWE-bench runs can require roughly 120 GB of free disk, so use a cloud machine and small worker count when local storage is limited. The 32-task prompt slice is for quick iteration; it does not change the need to evaluate the corresponding task environments.

## Comparing runs

Save one JSONL record per task for each run, with at least:

```json
{"instance_id":"owner__repo-123","resolved":true,"elapsed_seconds":482.1}
```

Then compare paired outcomes:

```bash
python tools/compare_runs.py \
  --baseline results/baseline/task_results.jsonl \
  --candidate results/candidate/task_results.jsonl \
  --bootstrap 10000 \
  --seed 42
```

The report includes resolution rates, paired percentage-point change, a paired bootstrap 95% interval, discordant task counts, and per-repository results when `repo` is present in each row. It fails if the two runs do not contain the same unique task IDs. Preserve raw logs and patches outside this public repo; publish only aggregate results unless every task/data license permits more.

## Recommended protocol

1. Freeze a baseline and run ID. Record model variant, adapter SHA-256, agent config hash, prompt hash, seed, tool/time limits, harness version, task manifest hash, and cloud hardware.
2. Change one thing per candidate. Keep all other settings identical.
3. Compare task-by-task on a fixed development subset. Re-run promising changes on the repository-held-out split before adopting them.
4. Report resolved count/rate, paired change with interval, failures, wall time, tokens if available, and per-repository results. Avoid selecting by a small point-estimate change alone.
5. Only spend a daily submission slot after the candidate has passed the local comparison and the official format/runtime checks.

## Limitations

- SWE-bench Verified is public and may overlap model training data. Its 500 expert-checked Python issue tasks improve breadth over a 129-task development set, but do not make it more representative of the hidden Kaggle tasks by default.
- The competition and SWE-bench harnesses differ. Scores from the two lanes must not be pooled into one headline score.
- A passing local test suite does not guarantee a hidden task passes. Treat competition dev-set results as directional evidence.
- This kit does not run Gemma inference. It standardizes task manifests and paired result analysis; use the same agent and model settings you intend to submit.

## Sources

- [Gemma 4 Developer Agent competition overview](https://www.kaggle.com/competitions/gemma-4-developer-agent/overview)
- [SWE-bench dataset guide](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/datasets.md)
- [SWE-bench repository and evaluator](https://github.com/SWE-bench/SWE-bench)
- [Pinned SWE-bench Verified dataset revision](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/tree/78f471bf655a3137b2e8a75af1501690ec009ec3)
