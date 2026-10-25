# How printing works on ChromeOS (for PPD authors)

ChromeOS prints through CUPS, but you can't install anything into it. A PPD
for ChromeOS can only use what ChromeOS already ships. This page lists what
that is and what ChromeOS checks. The machine-readable version the checker
uses is [`checker/chromeos-data.json`](../checker/chromeos-data.json).

Sources: chromiumos/platform2 (`foomatic_shell`, `debugd`) and
chromiumos-overlay (`net-print/*`, `app-text/ghostscript-gpl`), October 2026.

## Where PPDs come from

- **Driverless printers** (IPP Everywhere, AirPrint, IPP-USB) need no PPD.
- **Google's PPD index:** ChromeOS matches a printer's make/model or USB
  device ID against PPDs Google hosts (largely from OpenPrinting and vendors).
- **User-supplied PPD:** Settings → Printers → "specify your printer PPD".
- **Admin console:** a PPD URL per printer (USB or network) for managed devices.

## What ChromeOS checks when a printer is added

`debugd` (platform2 `debugd/src/cups_tool.cc`, `TestPPD`):

1. The PPD must be at least 200 bytes (gzip-compressed PPDs are allowed).
2. `cupstestppd -W translations -W constraints -` must pass. Any **FAIL**,
   including a `cupsFilter` program that doesn't exist on ChromeOS, refuses
   the printer.
3. If the PPD uses `foomatic-rip`, ChromeOS runs `foomatic-rip` with
   `FOOMATIC_VERIFY_MODE=true` on a tiny built-in 3×3-point PDF. Every command
   it would run must pass `foomatic_shell`'s rules (below).

Passing these doesn't guarantee printing: some problems only appear at print
time (for example `foomatic-rip` rewriting a `gs` command in PostScript mode).
The checker also runs a real print through the emulator for that reason.

## Filters ChromeOS ships

A PPD may name any of these in `*cupsFilter` / `*cupsFilter2`:

| Source | Filters |
|---|---|
| CUPS 2.4 | `commandtops`, `gziptoany`, `pstops`, `rastertoepson`, `rastertohp`, `rastertolabel` (DYMO, Zebra ZPL/EPL/CPCL, Intellitech), `rastertopwg` |
| cups-filters 1.28.17 | `foomatic-rip`, `pdftopdf`, `pdftops`, `gstoraster`/`pstoraster`, `gstopxl`/`pstopxl`, `gstopdf`, `rastertopclx`, `rastertoescpx`, `commandtopclx`, `commandtoescpx`, `rastertops`, `rastertopdf`, `texttopdf`, `texttotext`, `bannertopdf`, `imagetops`, `texttops`, `rastertopclm` |
| cups-filter-rastertoescpos | `rastertoescpos` (generic ESC/POS receipt printers) |
| tsc-cupsdrv | `rastertobarcodetspl` (TSC TSPL label printers) |
| starcupsdrv | `rastertostar`, `rastertostarlm`, `rastertostarm` |
| epson-receipt-printer-thermal | `rastertotmtr` (Epson TM) |
| dymo-cups-drivers | `raster2dymolw`, `raster2dymolm` |
| hplip | `hpcups`, `hpps` |
| pwgtocanonij | `pwgtocanonij` |
| epson-inkjet-printer-escpr | `epson-escpr`, `epson-escpr-wrapper` |
| epson-inkjet-printer-colorworks | `epson_colorworks` |
| hwasung-cupsdrv | `rastertohwasung` |
| custom-cupsdrv | `rasterto…` / `rasterTo…` per Custom model |

Anything else, in particular a vendor program like
`/Library/Printers/<Vendor>/rastertoXXX` from a Mac driver, does not exist on
ChromeOS, so the PPD is refused.

## `foomatic-rip` and `foomatic_shell`

`foomatic-rip` runs the PPD's `*FoomaticRIPCommandLine` through
`foomatic_shell`, which:

- runs only `cat`, `cut`, `date`, `echo`, `gs`, `pdftops`, `printf`, `sed`;
- supports `;`, `|`, `( )`, `` `…` `` and quoting, but **no redirection**
  (`<`, `>`);
- allows unquoted characters only from letters, digits and `. / _ - + @ %`
  (anything else must be quoted);
- requires `gs` to have `-dSAFER` and `-sOutputFile=-`, to read only stdin or
  files in `/tmp/` and `/var/spool/cups/`, and forbids `-c`, `-o`, `@file`,
  `NOSAFER`, `OutputFile`, `OutputICCProfile` and the name `stdout`;
- limits a script to 16 KB, CPU time to 15 minutes and memory to 256 MB.

Two `foomatic-rip` behaviours to know:

- **PostScript input:** a command starting with `gs` gets `-sstdout=%stderr`
  added, which `foomatic_shell` rejects. Run `gs` as `(gs …)` in that case.
- **PDF input:** `foomatic-rip` inserts the PDF's path into the **first** bare
  `gs` command; without one it appends `< file`, which `foomatic_shell` can't
  parse.

## Ghostscript devices

ChromeOS's Ghostscript has a fixed device list (`ghostscript_devices` in
`checker/chromeos-data.json`): the common printer drivers (`ljet4`, `pxlmono`,
`pcl3`, `epson`, `stcolor`, `uniprint`, …), `bit`, `ppmraw`, `pdfwrite`,
`ps2write` and `cups`. Image devices like `png16m` or `tiffg4` are **not**
included.
