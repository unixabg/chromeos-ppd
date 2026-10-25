# Thermal family: TSPL label printers and ESC/POS receipt printers

Each printer is described by a JSON **profile** in `profiles/`; `ppdgen.py`
turns it into a PPD in the top-level `ppd/` folder. The PPD runs one
Ghostscript `uniprint` command that writes the printer's own commands around
every page's 1-bit image, so multi-page documents print as separate labels or
one continuous receipt.

| File | What it is |
|---|---|
| `profiles/*.json` | one per printer: language, bitmap polarity, commands, sizes, test notes |
| `ppdgen.py` | profile → PPD (`--all` regenerates every profile) |
| `probe.py` | sends numbered test prints to a printer and writes a draft profile from your answers |
| `preview.py` | renders a TSPL or ESC/POS job to PNG |
| `bitmap.py` | test-image helper for the probe |
| [how-it-works.md](how-it-works.md) | the technique and the ChromeOS traps |
| [adding-a-printer.md](adding-a-printer.md) | step by step, about 15 minutes with the printer |

Supported languages: TSPL and ESC/POS. ZPL, EPL and CPCL should work the same
way (see the end of adding-a-printer.md). Note that ChromeOS also ships
filters for some of these printers itself (`rastertoescpos`,
`rastertobarcodetspl`, `rastertolabel`, …), so a PPD built on one of those is
another valid route for a printer that accepts its output.
