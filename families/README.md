# Printer families

A family is a kind of printer that can share one approach to working on
ChromeOS, and the tools for it. Each family has its own folder; every
family's PPDs go into the top-level [`ppd/`](../ppd) folder, and all of them
must pass the [checker](../checker/README.md).

| Family | Printers | Approach | Folder |
|---|---|---|---|
| thermal | label and receipt printers speaking TSPL or ESC/POS | Ghostscript `uniprint` writes the printer's own bytes around each page's 1-bit image; profiles → generator; probe tool to discover a printer's quirks | [thermal/](thermal/README.md) |

## Adding a family

Typical candidates: printers whose language ChromeOS's Ghostscript can produce
(PCL, ESC/P via `ljet4`, `pxlmono`, `pcl3`, `epson`, `stcolor`, `uniprint`, …)
but that ChromeOS doesn't match automatically, or printers that one of
ChromeOS's built-in filters can drive (`rastertolabel`, `rastertoescpos`,
`rastertobarcodetspl`, `rastertostar`, …; see
[docs/chromeos-printing.md](../docs/chromeos-printing.md)).

A family folder needs:

- a `README.md`: which printers, how it works, how to add one;
- the sources its PPDs are made from (profiles, a generator), or the
  hand-written PPDs' notes if they're written by hand;
- PPDs in `ppd/` named `<maker>-<model>.ppd`, each passing
  `python3 checker/chromeos_ppd_check.py`;
- a line per printer in the top-level README table.
