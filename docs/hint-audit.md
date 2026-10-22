# Hint audit: patch-like text in SWE-bench Verified prompts

A static scan of the pinned 500-task prompt manifest (revision `78f471bf655a3137b2e8a75af1501690ec009ec3`, manifest SHA-256 `004334986d6bb2977bd6b47a048405f3b6cebd477f05a60ffdda62af721b133a`).

| Measure | Count |
| --- | --- |
| Tasks with a non-empty `hints_text` | 338 of 500 |
| Hints with exact diff markers (`diff --git`, `@@`, `---`/`+++` headers) | 16 |
| Hints with paired plus/minus lines | 13 |
| Union flagged by either heuristic | 17 (3.4%) |
| Of those, flagged in development / holdout | 11 / 6 |
| Hints containing a code fence (not leak evidence on its own) | 83 |

A manual read of the marker-bearing lines classified 16 of the 17 as code or diff-like excerpts and one (`matplotlib__matplotlib-25122`) as a discussion bullet that happened to match. The quoted material was **not** compared with the reference patches, and no model was run, so this is a prompt-hygiene caution and not evidence of leakage or of any effect on resolution.

The 17 IDs are in [`tiers/hint_patch_signal.ids`](../tiers/hint_patch_signal.ids). Their distribution over the tiers: `smoke8` 0, `dev32` 0, `dev96` 6, `dev-all` 11, `holdout` 6.

Suggested use: keep the full-prompt lane primary. When a candidate looks better, repeat the comparison with `--blank-hints` manifests (see the README) or with these IDs excluded, and report both. Kaggle's own prompts are a different corpus; this audit says nothing about them.
