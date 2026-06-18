#!/usr/bin/env python3
"""Engine for flashforge-orca-presets.

Given an extracted FlashForge (Flash Studio) profile tree and upstream
OrcaSlicer's bundled `Flashforge` vendor, for each category (machine / filament /
process):

  * resolve every preset's `inherits` chain into a flat, self-contained preset;
  * classify each FlashForge preset against upstream by *resolved effective*
    config (cosmetic keys like `version` ignored): missing / newer / identical;
  * write the missing + newer ones (flattened, marked `from: User`) to the output;
  * report counts and any unresolved `inherits` parents.

Pure functions (`load_category`, `resolve`, `effective`, `importable`,
`classify`) are unit/fuzz-tested in test_ff_orca.py.

Usage:
    ff_orca.py fetch [-o OUT]              download Flash Studio + OrcaSlicer, build (default)
    ff_orca.py build <fs> <up> <out>      build from already-extracted profile trees

where <fs>/<up> each hold Flashforge/ (+ OrcaFilamentLibrary/) — from the Flash
Studio AppImage and the OrcaSlicer repo respectively.
"""
from __future__ import annotations
import argparse, glob, json, os, shutil, subprocess, sys, tempfile, urllib.request, zipfile

# --- defaults (bump when FlashForge ships a newer Flash Studio) --------------
FS_URL = ("https://flashforge-resource.oss-us-east-1.aliyuncs.com/"
          "Flash%20Studio/Flash_Studio_ubuntu24.04_V1.7.8-.zip")
FS_VER = "1.7.8"
UP_REPO = "https://github.com/SoftFever/OrcaSlicer"
UP_PATHS = ("resources/profiles/Flashforge", "resources/profiles/OrcaFilamentLibrary")

CATEGORIES = ("machine", "filament", "process")
# valid OrcaSlicer preset `type`s per category (machine has the model umbrella +
# the per-nozzle instances); a preset whose resolved type isn't here is mis-filed.
EXPECTED_TYPES = {
    "machine": {"machine", "machine_model"},
    "filament": {"filament"},
    "process": {"process"},
}
# resolution searches the FF vendor + the shared filament library
VENDORS = ("Flashforge", "OrcaFilamentLibrary")
# keys that differ for bookkeeping reasons, not slicing behaviour
COSMETIC = {
    "version", "from", "setting_id", "is_custom_defined", "instantiation",
    "name", "printer_agent", "filament_id", "filament_settings_id",
    "print_settings_id", "printer_settings_id", "user_id",
}


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def load_category(root: str, category: str) -> dict[str, tuple[dict, str]]:
    """name -> (raw config, source path) for every preset in this category."""
    out: dict[str, tuple[dict, str]] = {}
    for vendor in VENDORS:
        for fp in sorted(glob.glob(os.path.join(root, vendor, category, "*.json"))):
            try:
                d = json.load(open(fp, encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                print(f"  warn: skipping unreadable {fp}: {e}", file=sys.stderr)
                continue
            out[d.get("name") or _stem(fp)] = (d, fp)
    return out


def resolve(name: str, tree: dict[str, tuple[dict, str]],
            unresolved: set | None = None, _seen: frozenset = frozenset()) -> dict:
    """Merge the full `inherits` chain (root-most first, child overrides).

    A missing parent is recorded in `unresolved` (its keys are simply absent
    rather than silently pretending the chain ended cleanly). Cycle-safe.
    """
    if name in _seen:
        return {}
    if name not in tree:
        if unresolved is not None and name:
            unresolved.add(name)
        return {}
    cfg = tree[name][0]
    parent = cfg.get("inherits", "")
    merged = dict(resolve(parent, tree, unresolved, _seen | {name})) if parent else {}
    for k, v in cfg.items():
        if k != "inherits":
            merged[k] = v
    return merged


def effective(cfg: dict) -> dict:
    """Config with cosmetic/bookkeeping keys dropped, for comparison."""
    return {k: v for k, v in cfg.items() if k not in COSMETIC}


def importable(flat: dict, name: str) -> dict:
    """A resolved preset turned into a self-contained OrcaSlicer User preset."""
    out = {k: v for k, v in flat.items() if k != "inherits"}
    out["name"] = name
    out["from"] = "User"
    out["is_custom_defined"] = "1"
    return out


def classify(name: str, fs_tree: dict, up_tree: dict,
             unresolved: set | None = None) -> str:
    """'missing' | 'newer' | 'identical' by resolved effective config."""
    if name not in up_tree:
        return "missing"
    fs = effective(resolve(name, fs_tree, unresolved))
    up = effective(resolve(name, up_tree))
    return "identical" if fs == up else "newer"


def build(fs_root: str, up_root: str, out_dir: str, version: str = "") -> dict:
    stats: dict[str, dict] = {}
    plate_refs: set[str] = set()
    for cat in CATEGORIES:
        fs_tree = load_category(fs_root, cat)
        up_tree = load_category(up_root, cat)
        # Flatten against FS first, falling back to upstream for base-library
        # presets the Flash Studio AppImage doesn't ship (OrcaSlicer has them
        # built in). FS entries win where both exist.
        resolve_tree = {**up_tree, **fs_tree}
        out_cat = os.path.join(out_dir, cat)
        os.makedirs(out_cat, exist_ok=True)
        counts = {"missing": 0, "newer": 0, "identical": 0}
        unresolved: set[str] = set()
        # only FlashForge-vendor presets are candidates (not the shared library)
        for fp in sorted(glob.glob(os.path.join(fs_root, "Flashforge", cat, "*.json"))):
            raw = json.load(open(fp, encoding="utf-8"))
            # Skip abstract `inheritance` bases (e.g. fdm_machine_common): they are
            # not user-selectable presets, only parents to resolve against — and
            # flattening already inlines them into each real preset.
            if str(raw.get("instantiation", "true")).lower() == "false":
                counts["bases"] = counts.get("bases", 0) + 1
                continue
            name = raw.get("name") or _stem(fp)
            flat = importable(resolve(name, resolve_tree, unresolved), name)
            # Guard against presets mis-filed in the wrong category dir (FlashForge
            # ships a couple of machine configs inside filament/). Ship only if the
            # resolved `type` matches this category.
            if flat.get("type") not in EXPECTED_TYPES[cat]:
                counts["misfiled"] = counts.get("misfiled", 0) + 1
                continue
            kind = classify(name, fs_tree, up_tree, unresolved)
            counts[kind] += 1
            if kind == "identical":
                continue
            if cat == "machine":
                for key in ("bed_custom_texture", "bed_custom_model"):
                    v = flat.get(key)
                    if isinstance(v, str) and v:
                        plate_refs.add(os.path.basename(v))
            json.dump(flat, open(os.path.join(out_cat, os.path.basename(fp)), "w", encoding="utf-8"),
                      indent=4, ensure_ascii=False)
        if unresolved:
            print(f"  note: {cat}: {len(unresolved)} inherits parent(s) not found "
                  f"(keys absent): {', '.join(sorted(unresolved)[:5])}"
                  f"{' …' if len(unresolved) > 5 else ''}", file=sys.stderr)
        stats[cat] = counts
        extra = f", {counts['misfiled']} mis-filed-skipped" if counts.get("misfiled") else ""
        print(f"    {cat}: {counts['missing'] + counts['newer']} shipped "
              f"({counts['missing']} missing + {counts['newer']} newer), "
              f"{counts['identical']} identical-skipped{extra}")
    _copy_plates(fs_root, out_dir, plate_refs)
    _write_report(out_dir, stats, version)
    return stats


def _copy_plates(fs_root: str, out_dir: str, refs: set[str]) -> None:
    if not refs:
        return
    import shutil
    dst = os.path.join(out_dir, "buildplates")
    os.makedirs(dst, exist_ok=True)
    found = 0
    for a in sorted(refs):
        for src in glob.glob(os.path.join(fs_root, "Flashforge", "**", a), recursive=True):
            shutil.copy2(src, dst)
            found += 1
            break
    if not found:
        os.rmdir(dst)


def _write_report(out_dir: str, stats: dict, version: str) -> None:
    lines = [
        f"# Delta report — Flash Studio {version or '?'} vs upstream OrcaSlicer",
        "",
        "FlashForge presets upstream OrcaSlicer lacks (missing) or carries an older",
        "copy of (newer, by *resolved effective* config — cosmetic keys ignored).",
        "Byte/behaviour-identical presets are skipped. Regenerate with `ff_orca.py fetch`.",
        "",
        "| category | shipped | missing upstream | newer than upstream | identical (skipped) | FF total |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cat in CATEGORIES:
        c = stats[cat]
        tot = c["missing"] + c["newer"] + c["identical"]
        lines.append(f"| {cat} | {c['missing'] + c['newer']} | {c['missing']} | "
                     f"{c['newer']} | {c['identical']} | {tot} |")
    open(os.path.join(out_dir, "DELTA-REPORT.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


def _run(cmd, **kw):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)


def _extract_appimage(appimage: str, workdir: str) -> str:
    """Extract an AppImage's payload, returning squashfs-root/. Tries the bundled
    runtime, then falls back to unsquashfs at the ELF's appimage offset."""
    os.chmod(appimage, 0o755)
    root = os.path.join(workdir, "squashfs-root")
    try:
        _run([appimage, "--appimage-extract"], cwd=workdir)
    except (subprocess.CalledProcessError, OSError):
        off = subprocess.check_output([appimage, "--appimage-offset"], text=True).strip()
        _run(["unsquashfs", "-q", "-f", "-o", off, "-d", root, appimage])
    return root


def fetch(out_dir: str, fs_url: str = FS_URL, fs_ver: str = FS_VER,
          up_repo: str = UP_REPO) -> dict:
    """Full pipeline: download Flash Studio + upstream OrcaSlicer, then build()."""
    w = tempfile.mkdtemp(prefix="ff-orca-")
    try:
        print(f"[1/3] download + extract Flash Studio {fs_ver} ...")
        zip_path = os.path.join(w, "fs.zip")
        urllib.request.urlretrieve(fs_url, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(w)
        appimages = glob.glob(os.path.join(w, "*.AppImage"))
        if not appimages:
            raise SystemExit("no .AppImage inside the Flash Studio zip")
        fs = os.path.join(_extract_appimage(appimages[0], w), "resources", "profiles")
        if not os.path.isdir(os.path.join(fs, "Flashforge")):
            raise SystemExit("no Flashforge profiles in the AppImage")

        print("[2/3] fetch upstream OrcaSlicer Flashforge vendor (sparse) ...")
        oca = os.path.join(w, "oca")
        _run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", "-q", up_repo, oca])
        _run(["git", "-C", oca, "sparse-checkout", "set", *UP_PATHS])
        up = os.path.join(oca, "resources", "profiles")
        if not os.path.isdir(os.path.join(up, "Flashforge")):
            raise SystemExit("upstream Flashforge vendor not found")

        print("[3/3] flatten + diff + write ...")
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        return build(fs, up, out_dir, fs_ver)
    finally:
        shutil.rmtree(w, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    pf = sub.add_parser("fetch", help="download Flash Studio + OrcaSlicer, then build (default)")
    pf.add_argument("-o", "--out", default="import-into-orca")
    pf.add_argument("--fs-url", default=FS_URL)
    pf.add_argument("--fs-ver", default=FS_VER)

    pb = sub.add_parser("build", help="build from already-extracted local profile trees")
    pb.add_argument("fs_profiles")
    pb.add_argument("upstream_profiles")
    pb.add_argument("out_dir")
    pb.add_argument("--version", default="")

    a = ap.parse_args(argv)
    if a.cmd in (None, "fetch"):
        out = getattr(a, "out", "import-into-orca")
        fetch(out, getattr(a, "fs_url", FS_URL), getattr(a, "fs_ver", FS_VER))
    else:
        for cat in CATEGORIES:
            if not os.path.isdir(os.path.join(a.fs_profiles, "Flashforge", cat)):
                print(f"error: {a.fs_profiles}/Flashforge/{cat} missing", file=sys.stderr)
                return 1
        build(a.fs_profiles, a.upstream_profiles, a.out_dir, a.version)
        out = a.out_dir
    total = sum(len(glob.glob(os.path.join(out, c, "*.json"))) for c in CATEGORIES)
    print(f"done: {total} presets in {out}/ (see DELTA-REPORT.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
