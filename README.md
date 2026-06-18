# flashforge-orca-presets

![ci](https://github.com/maci0/flashforge-orca-presets/actions/workflows/ci.yml/badge.svg)

**FlashForge's current slicer presets — extracted from Flash Studio, flattened to
import straight into stock [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer).**

OrcaSlicer already bundles a FlashForge vendor, but it tracks FlashForge's own
slicer (**Flash Studio** — FF's OrcaSlicer fork, formerly Orca-Flashforge) with a
lag. This repo carries every FlashForge preset that upstream OrcaSlicer is
**missing** or ships an **older copy** of, each one *flattened* so it imports
cleanly without FlashForge's vendor profiles installed.

> Not affiliated with or endorsed by FlashForge. The profile data is
> FlashForge's, redistributed for interoperability — see [`NOTICE.md`](NOTICE.md).

## Quick start

1. **Get the files** — on GitHub, **Code → Download ZIP** (then unzip), or:
   ```sh
   git clone https://github.com/maci0/flashforge-orca-presets
   ```
2. **OrcaSlicer → File → Import → Import Configs…**
3. Select the `.json` files for your printer from
   [`import-into-orca/`](import-into-orca) — your **machine** first, then the
   **filament** / **process** presets you want. They appear as **User** presets.

See [Which files do I import?](#which-files-do-i-import) to pick the right ones.

## What's inside

Generated from **Flash Studio 1.7.8** vs upstream OrcaSlicer's `Flashforge` vendor
(full breakdown in [`import-into-orca/DELTA-REPORT.md`](import-into-orca/DELTA-REPORT.md)):

| category | shipped | missing upstream | newer than upstream | identical (skipped) |
|---|---:|---:|---:|---:|
| **machine** (printers) | **52** | 7 | 45 | 1 |
| **filament** | **593** | 130 | 463 | 0 |
| **process** (quality) | **121** | 20 | 101 | 0 |
| **total** | **766** | 157 | 609 | 1 |

- **Missing** = upstream doesn't have it at all (e.g. **Adventurer A5**,
  **Creator 5 / 5 Pro**, FF's PLA Galaxy / Luminous / Sparkle / Metal, the CF/GF
  line). **Newer** = upstream has the preset but an older copy — for machines that
  means updated start g-code, motion limits, retraction, bed-mesh, and newer
  features (power-loss recovery, resonance avoidance, wrapping detection).
  Upstream's FlashForge **filament** profiles are essentially all stale.
  **Identical** presets are skipped — you already have those.
- The 52 machine presets cover **11 models** (Adventurer 5M / 5M Pro / A5, AD5X,
  3 Series, Creator 5 / 5 Pro, Guider 2s / 3 Ultra / 4 / 4 Pro) across their
  nozzle sizes. The 593 filaments are FlashForge's catalogue + FusRock + a few
  FF-tuned generics.

## Which files do I import?

Filenames tell you the printer. For your machine, pick the matching files:

| folder | filename pattern | example |
|---|---|---|
| `machine/`  | `Flashforge <Model> <nozzle> Nozzle.json` | `Flashforge Adventurer 5M Pro 0.4 Nozzle.json` |
| `filament/` | `<Material> @FF <printer>[ <nozzle> nozzle].json` | `Flashforge PLA Galaxy @FF AD5M 0.25 nozzle.json` |
| `process/`  | `<layer> <quality> @… <printer> <nozzle> nozzle.json` | `0.20mm Standard @Flashforge AD5M Pro 0.4 Nozzle.json` |

The `@FF <printer>` (or `@Flashforge <printer>`) token binds a filament/process to
a printer. A filament with **no** nozzle suffix is the default (0.4 mm); a
`0.25 nozzle` suffix is the fine-nozzle tuning. Printer tokens you'll see:

| token | printer |
|---|---|
| `AD5M` | Adventurer 5M **and** 5M Pro (filaments use one token for both) |
| `AD5X` | Adventurer 5X |
| `Adventurer A5` | Adventurer A5 |
| `C5`, `C5P` | Creator 5 / Creator 5 Pro |
| `G4`, `G4P` | Guider 4 / Guider 4 Pro |
| `Guider 2s`, `Guider 3 Ultra` | Guider 2s / 3 Ultra |

**Worked example — Adventurer 5M Pro, 0.4 mm nozzle:**

1. `machine/Flashforge Adventurer 5M Pro 0.4 Nozzle.json`
2. process: any `process/… @Flashforge AD5M Pro 0.4 Nozzle.json`
3. filament: the FlashForge materials you print, e.g.
   `filament/Flashforge PLA Galaxy @FF AD5M 0.25 nozzle.json`

> **Filaments — read this.** Because this repo only carries what upstream is
> *missing or behind on*, an established printer like the 5M already has most of
> its everyday filaments **in stock OrcaSlicer** — what's added here is the newer
> materials (PLA Galaxy / Luminous / Sparkle, the CF/GF line) and fine-nozzle
> tunings. Newer printers (A5, Creator 5, Guider 4) get their **full** filament
> set here because upstream has none of it yet. If a `machine/` model is brand-new
> to OrcaSlicer (A5, Creator 5), also import its `Flashforge <Model>.json` model
> file — it hosts the nozzle variants.

Build-plate textures/models live in `import-into-orca/buildplates/`; OrcaSlicer
uses a default plate if you don't install them, so they're optional.

## FAQ

- **The printer doesn't appear after importing a filament/process.** Import the
  **machine** preset first — filaments/processes are filtered to compatible
  printers. If a whole *model* is new to OrcaSlicer, also import its
  `Flashforge <Model>.json` model file.
- **Will this break my OrcaSlicer?** No — everything imports as **User** presets
  alongside the built-ins. Remove any of them anytime from the preset manager.
- **Why isn't filament X here?** Only presets upstream OrcaSlicer lacks or ships
  *older* are included; the identical ones you already have.
- **These look out of date.** A weekly job rebuilds against the newest Flash
  Studio and the current OrcaSlicer — but you can always
  [regenerate](#updating) yourself.

## How it works

Each preset is **flattened**: its `inherits` chain (FlashForge vendor bases + the
shared OrcaFilamentLibrary) is resolved into one self-contained preset with
`inherits` removed and `from: "User"`, so stock OrcaSlicer takes it as a User
preset with no FlashForge vendor files required.

"Newer vs identical" is decided on the **resolved, effective** config — each
preset is fully resolved on both sides and compared with bookkeeping keys
(`version`, `setting_id`, `printer_agent`, …) ignored — so a preset counts as
"newer" only when its actual slicing behaviour differs, not when FlashForge merely
bumped a version string or moved a key between inheritance layers. Presets
mis-filed by FlashForge (e.g. a machine config inside `filament/`) are dropped by
a type check.

> A few FlashForge filaments inherit OrcaSlicer base presets (`fdm_filament_pla_silk`,
> …) that live inside the OrcaSlicer binary rather than as files; those base keys
> can't be inlined here, but OrcaSlicer fills them from its own defaults on import.

## Updating

A weekly GitHub Action ([`update.yml`](.github/workflows/update.yml)) runs
`ff_orca.py fetch --latest`, validates, and commits any change — so the repo
tracks both new Flash Studio releases and upstream OrcaSlicer catching up, with no
manual step. To run it yourself:

```sh
python3 ff_orca.py fetch --latest    # auto-detect newest Flash Studio, rebuild import-into-orca/
python3 ff_orca.py fetch             # or use the version pinned in ff_orca.py
```

`fetch` downloads Flash Studio (Ubuntu AppImage), sparse-clones upstream
OrcaSlicer's vendor + filament library in one git op, then flattens, diffs
(resolved config), and writes the missing/newer presets. Needs `python3`, `git`,
and `unzip` + either FUSE or `squashfs-tools` (for the AppImage). To build from
already-extracted trees instead of downloading:

```sh
python3 ff_orca.py build <flash-studio/resources/profiles> <orcaslicer/resources/profiles> import-into-orca
```

## Development

- [`ff_orca.py`](ff_orca.py) — the whole tool (acquire + flatten + diff + report).
  Pure functions (`resolve`, `effective`, `classify`, …) are isolated.
- [`test_ff_orca.py`](test_ff_orca.py) — unit + fuzz tests + shipped-output
  validation, no dependencies (run on every push by CI):

  ```sh
  python3 test_ff_orca.py        # 8 unit tests + 2000 fuzz iterations
  ```

## Licence

Tooling: MIT ([`LICENSE`](LICENSE)). Profile data: FlashForge's, redistributed
for interoperability ([`NOTICE.md`](NOTICE.md)).
