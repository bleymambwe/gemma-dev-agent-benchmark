from build_manifest import split_repositories
from make_tiers import TIER_SIZES, balanced_order, build_tiers

SEED = 7


def synthetic_rows():
    sizes = {"a/big": 80, "b/mid": 30, "c/mid2": 25, "d/small": 12, "e/tiny": 4, "f/holdout1": 15, "g/holdout2": 10}
    rows = [
        {"instance_id": f"{repo.replace('/', '__')}-{i}", "repo": repo}
        for repo, count in sizes.items()
        for i in range(count)
    ]
    for row in rows:
        row["split"] = "holdout" if row["repo"].startswith(("f/", "g/")) else "development"
    return rows


def test_tiers_are_nested_and_disjoint_from_holdout():
    tiers = build_tiers(synthetic_rows(), SEED)
    ids = {name: {row["instance_id"] for row in rows} for name, rows in tiers.items()}
    assert ids["smoke8"] < ids["dev32"] < ids["dev96"] < ids["dev-all"]
    assert not ids["holdout"] & ids["dev-all"]
    assert [len(tiers[name]) for name in TIER_SIZES] == list(TIER_SIZES.values())


def test_ordering_is_deterministic_and_seed_dependent():
    rows = synthetic_rows()
    first = [row["instance_id"] for row in balanced_order(rows, SEED)]
    assert first == [row["instance_id"] for row in balanced_order(list(reversed(rows)), SEED)]
    assert first != [row["instance_id"] for row in balanced_order(rows, SEED + 1)]


def test_small_tier_spans_repositories():
    development = [row for row in synthetic_rows() if row["split"] == "development"]
    smoke = balanced_order(development, SEED)[:5]
    assert len({row["repo"] for row in smoke}) == 5


def test_repository_split_keeps_repos_whole():
    rows = synthetic_rows()
    mapping = split_repositories(rows, seed=SEED, holdout_fraction=0.2)
    assert set(mapping.values()) == {"development", "holdout"}
    assert set(mapping) == {row["repo"] for row in rows}


def test_blank_hints_option_empties_written_manifests(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    rows = synthetic_rows()
    for row in rows:
        row.update(hints_text="see the fix: --- a/x +++ b/x", source_dataset="d", source_revision="r")
    manifest = tmp_path / "m.jsonl"
    manifest.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    tools = Path(__file__).resolve().parents[1] / "tools" / "make_tiers.py"
    for flag, expect_blank in (([], False), (["--blank-hints"], True)):
        out = tmp_path / ("blank" if expect_blank else "keep")
        subprocess.run(
            [sys.executable, str(tools), str(manifest), "--out", str(out / "ids"),
             "--write-manifests", str(out / "data"), "--seed", str(SEED), *flag],
            check=True, capture_output=True,
        )
        written = [json.loads(line) for line in (out / "data" / "tier-smoke8.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(written) == 8
        assert all((row["hints_text"] == "") is expect_blank for row in written)
