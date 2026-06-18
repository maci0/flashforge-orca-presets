#!/usr/bin/env python3
"""Unit + fuzz tests for ff_orca.py. Run: python3 test_ff_orca.py  (no deps)."""
import glob
import json
import os
import random
import ff_orca as M


def tree(d):
    """{name: config} -> the (config, path) shape load_category produces."""
    return {k: (v, f"{k}.json") for k, v in d.items()}


# --- unit -------------------------------------------------------------------

def test_resolve_merges_chain_child_wins():
    t = tree({
        "base":  {"a": 1, "b": 1},
        "mid":   {"inherits": "base", "b": 2, "c": 2},
        "leaf":  {"inherits": "mid", "c": 3, "d": 3},
    })
    assert M.resolve("leaf", t) == {"a": 1, "b": 2, "c": 3, "d": 3}
    assert "inherits" not in M.resolve("leaf", t)


def test_resolve_missing_parent_recorded_not_fatal():
    t = tree({"leaf": {"inherits": "ghost", "x": 1}})
    un = set()
    assert M.resolve("leaf", t, un) == {"x": 1}
    assert un == {"ghost"}


def test_resolve_cycle_safe():
    t = tree({"a": {"inherits": "b", "x": 1}, "b": {"inherits": "a", "y": 2}})
    # must terminate, not recurse forever
    out = M.resolve("a", t)
    assert out.get("x") == 1 and out.get("y") == 2


def test_resolve_unknown_name():
    assert M.resolve("nope", {}) == {}


def test_effective_drops_cosmetic():
    e = M.effective({"version": "9", "from": "System", "speed": 5, "name": "x"})
    assert e == {"speed": 5}


def test_importable_marks_user_and_strips_inherits():
    out = M.importable({"inherits": "b", "speed": 5}, "My Preset")
    assert out["name"] == "My Preset" and out["from"] == "User"
    assert out["is_custom_defined"] == "1" and "inherits" not in out


def test_classify_missing_newer_identical():
    fs = tree({"P": {"speed": 9, "version": "2"}})
    up_same = tree({"P": {"speed": 9, "version": "1"}})   # only cosmetic differs
    up_diff = tree({"P": {"speed": 5}})
    assert M.classify("P", fs, {}) == "missing"
    assert M.classify("P", fs, up_same) == "identical"
    assert M.classify("P", fs, up_diff) == "newer"


# --- shipped output (skipped if import-into-orca/ isn't built) --------------

def test_shipped_output_is_importable():
    root = "import-into-orca"
    if not os.path.isdir(root):
        return  # nothing built locally; CI builds first
    seen = 0
    for cat in M.CATEGORIES:
        for fp in glob.glob(os.path.join(root, cat, "*.json")):
            seen += 1
            d = json.load(open(fp, encoding="utf-8"))          # valid JSON
            assert "inherits" not in d, f"{fp} still has inherits"
            assert d.get("from") == "User", f"{fp} from != User"
            assert d.get("name"), f"{fp} has no name"
            assert d.get("type") in M.EXPECTED_TYPES[cat], \
                f"{fp} type {d.get('type')!r} not valid for {cat}"
    assert seen > 0, "import-into-orca/ exists but has no presets"


def test_orca_printer_bundles_are_well_formed():
    import zipfile
    bdir = "import-into-orca/bundles"
    if not os.path.isdir(bdir):
        return
    bundles = glob.glob(os.path.join(bdir, "*.orca_printer"))
    assert bundles, "bundles/ exists but has no .orca_printer files"
    for b in bundles:
        z = zipfile.ZipFile(b)
        names = set(z.namelist())
        assert "bundle_structure.json" in names, f"{b}: no manifest"
        m = json.loads(z.read("bundle_structure.json"))
        assert m.get("bundle_type") == "printer config bundle", f"{b}: wrong bundle_type"
        assert m.get("printer_config"), f"{b}: no printer in bundle"
        for arr in ("printer_config", "filament_config", "process_config"):
            for path in m.get(arr, []):
                assert path in names, f"{b}: manifest path {path!r} missing from zip"


# --- fuzz -------------------------------------------------------------------

def fuzz_resolve(iterations=2000, seed=0):
    """Random inheritance graphs (incl. cycles + dangling parents): resolve must
    always terminate, never raise, drop `inherits`, and honour child-overrides."""
    rnd = random.Random(seed)
    for it in range(iterations):
        n = rnd.randint(1, 8)
        names = [f"n{i}" for i in range(n)]
        cfg = {}
        for i, nm in enumerate(names):
            d = {f"k{rnd.randint(0,4)}": rnd.randint(0, 9) for _ in range(rnd.randint(0, 4))}
            # parent: another node (maybe later -> cycle), a dangling name, or none
            r = rnd.random()
            if r < 0.6:
                d["inherits"] = rnd.choice(names)
            elif r < 0.75:
                d["inherits"] = "dangling"
            cfg[nm] = d
        t = tree(cfg)
        for nm in names:
            un = set()
            out = M.resolve(nm, t, un)           # must not hang or raise
            assert "inherits" not in out
            # every key in the resolved output traces to some node's own value
            for k, v in out.items():
                assert any(k in c and c[k] == v for c in cfg.values())
            # a node with no inherits resolves to exactly its own (minus inherits)
            if "inherits" not in cfg[nm]:
                assert out == {k: v for k, v in cfg[nm].items() if k != "inherits"}
    return iterations


def main():
    units = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in units:
        fn()
    n = fuzz_resolve()
    print(f"PASS: {len(units)} unit tests + {n} fuzz iterations")


if __name__ == "__main__":
    main()
