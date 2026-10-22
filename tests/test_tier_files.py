import json
from pathlib import Path

TIERS = Path(__file__).resolve().parents[1] / "tiers"


def ids(name):
    return set((TIERS / f"{name}.ids").read_text(encoding="utf-8").split())


def test_committed_tiers_are_consistent():
    summary = json.loads((TIERS / "tiers.json").read_text(encoding="utf-8"))
    for name, info in summary["tiers"].items():
        assert len(ids(name)) == info["tasks"], name
    assert ids("smoke8") < ids("dev32") < ids("dev96") < ids("dev-all")
    assert not ids("holdout") & ids("dev-all")
    assert len(ids("dev-all")) + len(ids("holdout")) == 500
