# flashforge-orca-presets

**FlashForge's current slicer presets — from Flash Studio — packaged to import
straight into stock [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer).**

OrcaSlicer already bundles a FlashForge vendor, but it lags FlashForge's own
slicer (**Flash Studio**, FF's OrcaSlicer fork). This repo carries every
FlashForge preset that upstream OrcaSlicer is **missing** or holds an **older
copy** of — each one flattened so it imports cleanly without FlashForge's vendor
bases installed.

> Not affiliated with or endorsed by FlashForge. The profile data is
> FlashForge's, redistributed for interoperability — see [`NOTICE.md`](NOTICE.md).

## What's inside — Flash Studio 1.7.8 vs upstream OrcaSlicer

| category | shipped | missing upstream | newer than upstream | identical (skipped) | FF total |
|---|---:|---:|---:|---:|---:|
| **machine** (printers) | **57** | 7 | 50 | 2 | 59 |
| **filament** | **636** | 134 | 502 | 0 | 636 |
| **process** (quality) | **124** | 20 | 104 | 6 | 130 |
| **total** | **817** | 161 | 656 | 8 | 825 |

- **Missing** = the printer/filament/process doesn't exist in upstream at all
  (e.g. **Adventurer A5**, **Creator 5 / 5 Pro**, FF's PLA Galaxy/Luminous/
  Sparkle/Metal, the CF/GF line).
- **Newer** = upstream has the same-named preset but an older copy. FlashForge's
  is newer — on machines that means updated `machine_start_gcode`, motion limits
  (`machine_max_*`), retraction, bed-mesh, and new features (power-loss recovery,
  resonance avoidance, wrapping detection). **All 636 filaments differ** from
  upstream — upstream's FlashForge filament profiles are entirely stale.
- **Skipped** = byte-identical to upstream; no reason to ship a duplicate.

`import-into-orca/DELTA-REPORT.md` is regenerated on every build.

## Importing into OrcaSlicer

1. **OrcaSlicer → File → Import → Import Configs…**
2. Select the `.json` files you want from `import-into-orca/filament/` (and
   `process/` / `machine/`). Multi-select works.
3. They land as **User** presets, filtered to compatible printers.

Each preset is **flattened**: its `inherits` chain (FF vendor bases + the shared
OrcaFilamentLibrary) is fully resolved into one self-contained preset with
`from: "User"`, so it imports into stock OrcaSlicer with no FlashForge vendor
files required. Machine defs reference build-plate assets in `buildplates/` via
`bed_custom_texture`/`bed_custom_model`; OrcaSlicer falls back to a default plate
if they aren't installed, so they're optional.

## Regenerating / updating

```sh
./build-ff-import.sh
```

Downloads the latest Flash Studio (Ubuntu AppImage), extracts its profiles,
diffs them against upstream OrcaSlicer's `Flashforge` vendor, and writes the
missing/newer ones — flattened — into `import-into-orca/`. Needs `curl`, `unzip`,
`python3`, `gh`. When FlashForge ships a newer Flash Studio, bump `FS_URL` /
`FS_VER` at the top of the script and re-run.

- `build-ff-import.sh` — the pipeline.
- `flatten.py` — the OrcaSlicer inheritance resolver it calls.

## Caveat

The missing/newer/identical split is by **raw preset content** (filename +
byte-compare against upstream). A "newer" preset may differ partly because
FlashForge moved a key between inheritance layers rather than changing slicing
behaviour — but `machine_start_gcode`, the new feature keys, and `version` are
unambiguously newer. When in doubt, the shipped preset is FlashForge's current
authoritative tuning.

## Licence

Tooling: MIT ([`LICENSE`](LICENSE)). Profile data: FlashForge's, redistributed
for interoperability ([`NOTICE.md`](NOTICE.md)).
