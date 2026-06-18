#!/usr/bin/env python3
"""Flatten OrcaSlicer/Flash-Studio presets into self-contained, importable JSON.

Each FlashForge preset uses `inherits` to chain up through FF vendor bases and the
shared OrcaFilamentLibrary. Upstream OrcaSlicer doesn't have the FF-exclusive
bases, so a raw preset won't import cleanly. This walks the full inheritance
chain (across the whole extracted vendor tree) and merges it into one flat preset
with `inherits` removed and `from`/`is_custom_defined` set so OrcaSlicer takes it
as an importable user preset.

Usage:
    flatten.py <profiles_root> <category> <out_dir> [name-substr-filter]
      profiles_root : dir holding Flashforge/ (+ OrcaFilamentLibrary/)
      category      : filament | process | machine
      out_dir       : where flattened JSONs are written
If a filter is given, only presets whose `name` contains it are emitted; without
one, every preset directly under Flashforge/<category>/ is emitted.
"""
import json, os, sys, glob

def load_all(root, category):
    """name -> (config dict, source path) across Flashforge + OrcaFilamentLibrary."""
    by_name = {}
    for vendor in ("Flashforge", "OrcaFilamentLibrary"):
        for fp in glob.glob(os.path.join(root, vendor, category, "*.json")):
            try:
                d = json.load(open(fp))
            except Exception:
                continue
            n = d.get("name") or os.path.splitext(os.path.basename(fp))[0]
            by_name[n] = (d, fp)
    return by_name

def resolve(name, by_name, seen=None):
    """Merge the full inherits chain (root-most first, child overrides)."""
    seen = seen or set()
    if name in seen or name not in by_name:
        return {}
    seen.add(name)
    cfg, _ = by_name[name]
    parent = cfg.get("inherits", "")
    merged = resolve(parent, by_name, seen) if parent else {}
    for k, v in cfg.items():
        if k in ("inherits",):
            continue
        merged[k] = v
    return merged

def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    root, category, out = sys.argv[1], sys.argv[2], sys.argv[3]
    filt = sys.argv[4] if len(sys.argv) > 4 else None
    by_name = load_all(root, category)
    os.makedirs(out, exist_ok=True)
    n = 0
    for fp in sorted(glob.glob(os.path.join(root, "Flashforge", category, "*.json"))):
        d = json.load(open(fp))
        name = d.get("name") or os.path.splitext(os.path.basename(fp))[0]
        if filt and filt not in name:
            continue
        flat = resolve(name, by_name)
        flat.pop("inherits", None)
        flat["name"] = name
        flat["from"] = "User"
        flat["is_custom_defined"] = "1"
        # keep printer/process/filament type keys OrcaSlicer expects as-is
        json.dump(flat, open(os.path.join(out, os.path.basename(fp)), "w"),
                  indent=4, ensure_ascii=False)
        n += 1
    print(f"flattened {n} {category} presets -> {out}")

if __name__ == "__main__":
    main()
