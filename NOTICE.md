# Notice / provenance

The **tooling** in this repo (`ff_orca.py`, `test_ff_orca.py`) is MIT-licensed
(see `LICENSE`).

The **profile data** under `import-into-orca/` is **not** original work — it is
extracted from FlashForge's *Flash Studio* slicer (FlashForge's fork of
OrcaSlicer) and redistributed here, unmodified except for flattening each
preset's inheritance chain so it imports into stock OrcaSlicer. The presets are
FlashForge's; trademarks ("FlashForge", "Flash Studio", model names) belong to
their owner. This repo claims no ownership of them and is not affiliated with or
endorsed by FlashForge.

It exists for **interoperability**: OrcaSlicer already bundles FlashForge vendor
profiles, but lags the current Flash Studio release; this packages the newer/
missing ones so OrcaSlicer users get FlashForge's current tuning. If FlashForge
requests removal, the data will be taken down.

Generated from Flash Studio 1.7.8; regenerate with `python3 ff_orca.py fetch`.
