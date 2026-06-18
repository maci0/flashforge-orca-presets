# flashforge-orca-presets

**FlashForge's current slicer presets — extracted from Flash Studio, flattened to
import straight into stock [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer).**

OrcaSlicer already bundles a FlashForge vendor, but it tracks FlashForge's own
slicer (**Flash Studio** — FF's OrcaSlicer fork, formerly Orca-Flashforge) with a
lag. This repo carries every FlashForge preset that upstream OrcaSlicer is
**missing** or ships an **older copy** of, each one *flattened* so it imports
cleanly without FlashForge's vendor profiles installed.

> Not affiliated with or endorsed by FlashForge. The profile data is
> FlashForge's, redistributed for interoperability — see [`NOTICE.md`](NOTICE.md).

## What's inside

Generated from **Flash Studio 1.7.8** vs upstream OrcaSlicer's `Flashforge` vendor
(also in [`import-into-orca/DELTA-REPORT.md`](import-into-orca/DELTA-REPORT.md)):

| category | shipped | missing upstream | newer than upstream | identical (skipped) |
|---|---:|---:|---:|---:|
| **machine** | **52** | 7 | 45 | 1 |
| **filament** | **595** | 132 | 463 | 0 |
| **process** | **121** | 20 | 101 | 0 |
| **total** | **768** | 159 | 609 | 1 |

- The **52 machine presets** are printer×nozzle combinations (0.25 / 0.4 / 0.6 /
  0.8, plus HF) across **11 models**: Adventurer 5M, 5M Pro, A5, AD5X, 3 Series,
  Creator 5, Creator 5 Pro, Guider 2s, Guider 3 Ultra, Guider 4, Guider 4 Pro.
  *(Abstract `inheritance` bases like `fdm_machine_common` are **not** shipped —
  they aren't selectable printers; their values are already merged into each
  preset by flattening.)*
- The **595 filaments** are FlashForge's catalogue (PLA Galaxy / Luminous /
  Sparkle / Metal / Pro, PETG Pro/Transparent, the CF/GF line, …) plus FusRock
  and a few FF-tuned generics.
- **Missing** = upstream doesn't have it at all (e.g. Adventurer A5, Creator 5).
  **Newer** = upstream has the same preset but an older copy — for machines that's
  updated `machine_start_gcode`, motion limits (`machine_max_*`), retraction,
  bed-mesh, and newer features (power-loss recovery, resonance avoidance,
  wrapping detection). Upstream's FlashForge **filament** profiles are essentially
  all stale. **Identical** presets are skipped — no point shipping a duplicate.

## Install (import into OrcaSlicer)

1. **OrcaSlicer → File → Import → Import Configs…**
2. Select the `.json` files you want from `import-into-orca/filament/` (and
   `process/` / `machine/`). Multi-select works; import a whole folder at once.
3. They appear as **User** presets, filtered to compatible printers.

Build-plate assets the machine presets reference live in
`import-into-orca/buildplates/`; OrcaSlicer falls back to a default plate if they
aren't installed, so they're optional.

## How it works

Each preset is **flattened**: its `inherits` chain (FlashForge vendor bases + the
shared OrcaFilamentLibrary) is resolved into one self-contained preset with
`inherits` removed and `from: "User"`, so stock OrcaSlicer takes it as a User
preset with no FlashForge vendor files required.

"Newer vs identical" is decided on the **resolved, effective** config — each
preset is fully resolved on both sides and compared with bookkeeping keys
(`version`, `setting_id`, `printer_agent`, …) ignored — so a preset only counts
as "newer" when its actual slicing behaviour differs, not when FlashForge merely
bumped a version string or moved a key between inheritance layers.

> A handful of FlashForge filaments inherit OrcaSlicer base presets
> (`fdm_filament_pla_silk`, …) that ship inside the OrcaSlicer binary rather than
> as files; those base keys can't be inlined here, but OrcaSlicer supplies them
> from its own defaults on import. The build prints a note listing any such
> parents.

## Regenerating / updating

```sh
python3 ff_orca.py fetch          # downloads Flash Studio + OrcaSlicer, rebuilds import-into-orca/
```

`ff_orca.py fetch` runs the whole pipeline:

1. download the latest Flash Studio (Ubuntu AppImage) and extract its profiles;
2. sparse-clone upstream OrcaSlicer's `Flashforge` vendor + shared filament
   library (one git op);
3. flatten, diff (resolved config), and write the missing/newer presets.

Needs `curl`/`python3`, `unzip`, `git`. When FlashForge ships a newer Flash
Studio, bump `FS_URL` / `FS_VER` at the top of `ff_orca.py` and re-run.

To rebuild from already-extracted trees instead of downloading:

```sh
python3 ff_orca.py build <flash-studio/resources/profiles> <orcaslicer/resources/profiles> import-into-orca
```

## Development

- [`ff_orca.py`](ff_orca.py) — the whole tool (acquire + flatten + diff + report).
  Pure functions (`resolve`, `effective`, `classify`, …) are isolated and tested.
- [`test_ff_orca.py`](test_ff_orca.py) — unit + fuzz tests, no dependencies:

  ```sh
  python3 test_ff_orca.py        # 7 unit tests + 2000 fuzz iterations
  ```

## Licence

Tooling: MIT ([`LICENSE`](LICENSE)). Profile data: FlashForge's, redistributed
for interoperability ([`NOTICE.md`](NOTICE.md)).
