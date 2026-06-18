# Delta report — Flash Studio 1.7.8 vs upstream OrcaSlicer

FlashForge presets upstream OrcaSlicer lacks (missing) or carries an older
copy of (newer, by *resolved effective* config — cosmetic keys ignored).
Byte/behaviour-identical presets are skipped. Regenerate with `ff_orca.py fetch`.

| category | shipped | missing upstream | newer than upstream | identical (skipped) | FF total |
|---|---:|---:|---:|---:|---:|
| machine | 52 | 7 | 45 | 1 | 53 |
| filament | 595 | 132 | 463 | 0 | 595 |
| process | 121 | 20 | 101 | 0 | 121 |
