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

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

# --- defaults (bump when FlashForge ships a newer Flash Studio) --------------
FS_URL = (
    "https://flashforge-resource.oss-us-east-1.aliyuncs.com/"
    "Flash%20Studio/Flash_Studio_ubuntu24.04_V1.7.8-.zip"
)
FS_VER = "1.7.8"
UP_REPO = "https://github.com/SoftFever/OrcaSlicer"
UP_PATHS = ("resources/profiles/Flashforge", "resources/profiles/OrcaFilamentLibrary")
FS_PAGE = "https://www.flashforge.com/pages/orca-flashforge"
FS_OSS = "https://flashforge-resource.oss-us-east-1.aliyuncs.com/Flash%20Studio/"

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
    "version",
    "from",
    "setting_id",
    "is_custom_defined",
    "instantiation",
    "name",
    "printer_agent",
    "filament_id",
    "filament_settings_id",
    "print_settings_id",
    "printer_settings_id",
    "user_id",
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


def resolve(
    name: str,
    tree: dict[str, tuple[dict, str]],
    unresolved: set | None = None,
    _seen: frozenset = frozenset(),
) -> dict:
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


def classify(name: str, fs_tree: dict, up_tree: dict, unresolved: set | None = None) -> str:
    """'missing' | 'newer' | 'identical' by resolved effective config."""
    if name not in up_tree:
        return "missing"
    fs = effective(resolve(name, fs_tree, unresolved))
    up = effective(resolve(name, up_tree))
    return "identical" if fs == up else "newer"


def build(fs_root: str, up_root: str, out_dir: str, version: str = "") -> dict:
    stats: dict[str, dict] = {}
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
            json.dump(
                flat,
                open(os.path.join(out_cat, os.path.basename(fp)), "w", encoding="utf-8"),
                indent=4,
                ensure_ascii=False,
            )
        if unresolved:
            print(
                f"  note: {cat}: {len(unresolved)} inherits parent(s) not found "
                f"(keys absent): {', '.join(sorted(unresolved)[:5])}"
                f"{' …' if len(unresolved) > 5 else ''}",
                file=sys.stderr,
            )
        stats[cat] = counts
        extra = f", {counts['misfiled']} mis-filed-skipped" if counts.get("misfiled") else ""
        print(
            f"    {cat}: {counts['missing'] + counts['newer']} shipped "
            f"({counts['missing']} missing + {counts['newer']} newer), "
            f"{counts['identical']} identical-skipped{extra}"
        )
    _copy_plates(fs_root, out_dir)
    print("  bundling per printer ...")
    n = make_bundles(out_dir)
    print(f"  {n} .orca_printer bundles in {out_dir}/bundles/")
    _write_report(out_dir, stats, version)
    return stats


def _model_of(machine_name: str) -> str:
    """Strip a nozzle suffix to get the printer model (instances -> their model;
    the model umbrella preset is already the bare model name)."""
    return re.sub(r"\s+\d(\.\d+)?\s*(HF\s+)?[Nn]ozzle.*$", "", machine_name).strip()


def make_bundles(out_dir: str) -> int:
    """Group the built presets into one .orca_printer bundle per printer model —
    a zip of printer/ + filament/ + process/ presets with a bundle_structure.json,
    the format OrcaSlicer's "Import Configs" reads. Returns the bundle count.

    Filament/process are assigned to a model via each preset's `compatible_printers`
    (the authoritative binding) rather than the inconsistent filename tokens.
    """
    import zipfile

    def load(cat):  # filename -> (name, config)
        out = {}
        for fp in sorted(glob.glob(os.path.join(out_dir, cat, "*.json"))):
            d = json.load(open(fp, encoding="utf-8"))
            out[os.path.basename(fp)] = (d.get("name", _stem(fp)), d)
        return out

    machines, filaments, processes = load("machine"), load("filament"), load("process")
    # model -> machine files; and machine-name -> model (for compatible_printers lookup)
    model_machines: dict[str, list[str]] = {}
    name_model: dict[str, str] = {}
    for fn, (name, _) in machines.items():
        model = _model_of(name)
        model_machines.setdefault(model, []).append(fn)
        name_model[name] = model

    def models_for(cfg) -> set[str]:
        cp = cfg.get("compatible_printers") or []
        if isinstance(cp, str):
            cp = [cp]
        return {name_model[p] for p in cp if p in name_model}

    model_fil: dict[str, list[str]] = {}
    model_proc: dict[str, list[str]] = {}
    for fn, (_, cfg) in filaments.items():
        for m in models_for(cfg):
            model_fil.setdefault(m, []).append(fn)
    for fn, (_, cfg) in processes.items():
        for m in models_for(cfg):
            model_proc.setdefault(m, []).append(fn)

    bdir = os.path.join(out_dir, "bundles")
    if os.path.isdir(bdir):
        shutil.rmtree(bdir)
    os.makedirs(bdir)
    made = 0
    for model, mfiles in sorted(model_machines.items()):
        ffiles = sorted(model_fil.get(model, []))
        pfiles = sorted(model_proc.get(model, []))
        manifest = {
            "version": "",
            "bundle_id": "flashforge-orca-presets",
            "bundle_type": "printer config bundle",
            "printer_preset_name": model,
            "printer_config": [f"printer/{f}" for f in sorted(mfiles)],
            "filament_config": [f"filament/{f}" for f in ffiles],
            "process_config": [f"process/{f}" for f in pfiles],
        }
        safe = re.sub(r"[^\w.-]+", "_", model).strip("_")
        with zipfile.ZipFile(
            os.path.join(bdir, f"{safe}.orca_printer"), "w", zipfile.ZIP_DEFLATED
        ) as z:
            for f in mfiles:
                z.write(os.path.join(out_dir, "machine", f), f"printer/{f}")
            for f in ffiles:
                z.write(os.path.join(out_dir, "filament", f), f"filament/{f}")
            for f in pfiles:
                z.write(os.path.join(out_dir, "process", f), f"process/{f}")
            z.writestr("bundle_structure.json", json.dumps(manifest))
        made += 1
        print(f"    bundle: {model} ({len(mfiles)}p + {len(ffiles)}f + {len(pfiles)}proc)")
    return made


def _copy_plates(fs_root: str, out_dir: str) -> None:
    """Copy FlashForge's build-plate assets (bed textures + 3D models). The flat
    presets clear `bed_custom_texture`, so these are shipped as standalone art the
    user can install for the custom bed preview — see the README."""
    dst = os.path.join(out_dir, "buildplates")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    found = 0
    for src in glob.glob(os.path.join(fs_root, "Flashforge", "**", "*uildplate*"), recursive=True):
        if os.path.isfile(src):
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(src, dst)
            found += 1
    print(f"    build-plate assets: {found}")


def _write_report(out_dir: str, stats: dict, version: str) -> None:
    lines = [
        f"# Delta report — Flash Studio {version or '?'} vs upstream OrcaSlicer",
        "",
        "FlashForge presets upstream OrcaSlicer lacks (missing) or carries an older",
        "copy of (newer, by *resolved effective* config — cosmetic keys ignored).",
        "Byte/behaviour-identical presets are skipped. Regenerate with `ff_orca.py fetch`.",
        "",
        "| category | shipped | missing upstream | newer than upstream | identical (skipped) | FF total |",  # noqa: E501
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cat in CATEGORIES:
        c = stats[cat]
        tot = c["missing"] + c["newer"] + c["identical"]
        lines.append(
            f"| {cat} | {c['missing'] + c['newer']} | {c['missing']} | "
            f"{c['newer']} | {c['identical']} | {tot} |"
        )
    open(os.path.join(out_dir, "DELTA-REPORT.md"), "w", encoding="utf-8").write(
        "\n".join(lines) + "\n"
    )


def _run(cmd, **kw):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)


def _extract_appimage(appimage: str, workdir: str) -> str:
    """Extract an AppImage's payload, returning squashfs-root/. Tries the bundled
    runtime (needs FUSE), then falls back to unsquashfs at the ELF's appimage
    offset (e.g. CI runners, which have no FUSE)."""
    os.chmod(appimage, 0o755)
    root = os.path.join(workdir, "squashfs-root")
    try:
        _run([appimage, "--appimage-extract"], cwd=workdir)
    except (subprocess.CalledProcessError, OSError):
        pass
    # If FUSE extraction did nothing (raised, or silently no-op), unsquashfs it.
    if not os.path.isdir(os.path.join(root, "resources")):
        off = subprocess.check_output([appimage, "--appimage-offset"], text=True).strip()
        _run(["unsquashfs", "-q", "-f", "-o", off, "-d", root, appimage])
    return root


def _ver_tuple(s: str) -> tuple:
    m = re.search(r"V([0-9]+(?:\.[0-9]+)*)", s)
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def latest_fs_url(page: str = FS_PAGE) -> tuple[str, str]:
    """Scrape FlashForge's download page for the newest Flash Studio Ubuntu build.
    Returns (url, version) or ("", "") if none found (caller falls back to FS_URL)."""
    try:
        html = urllib.request.urlopen(page, timeout=30).read().decode("utf-8", "replace")
    except OSError:
        return "", ""
    names = re.findall(r"Flash_Studio_ubuntu[^\"'<>\s]*\.zip", html)
    if not names:
        return "", ""
    fn = max(set(names), key=_ver_tuple)
    ver = re.search(r"V([0-9.]+)", fn)
    return FS_OSS + urllib.parse.quote(fn), (ver.group(1).rstrip(".") if ver else "")


def fetch(
    out_dir: str,
    fs_url: str = FS_URL,
    fs_ver: str = FS_VER,
    up_repo: str = UP_REPO,
    latest: bool = False,
) -> dict:
    """Full pipeline: download Flash Studio + upstream OrcaSlicer, then build()."""
    if latest:
        url, ver = latest_fs_url()
        if url:
            fs_url, fs_ver = url, ver or fs_ver
            print(f"[0/3] latest Flash Studio detected: {fs_ver}")
        else:
            print("[0/3] could not detect latest; using pinned FS_URL", file=sys.stderr)
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
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd")

    pf = sub.add_parser("fetch", help="download Flash Studio + OrcaSlicer, then build (default)")
    pf.add_argument("-o", "--out", default="import-into-orca")
    pf.add_argument("--fs-url", default=FS_URL)
    pf.add_argument("--fs-ver", default=FS_VER)
    pf.add_argument(
        "--latest",
        action="store_true",
        help="auto-detect the newest Flash Studio from flashforge.com",
    )

    pb = sub.add_parser("build", help="build from already-extracted local profile trees")
    pb.add_argument("fs_profiles")
    pb.add_argument("upstream_profiles")
    pb.add_argument("out_dir")
    pb.add_argument("--version", default="")

    a = ap.parse_args(argv)
    if a.cmd in (None, "fetch"):
        out = getattr(a, "out", "import-into-orca")
        fetch(
            out,
            getattr(a, "fs_url", FS_URL),
            getattr(a, "fs_ver", FS_VER),
            latest=getattr(a, "latest", False),
        )
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
