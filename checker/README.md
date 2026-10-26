# ChromeOS PPD checker

```
bash checker/emulator/build.sh                         # once
python3 checker/chromeos_ppd_check.py PPD [PPD ...] [--pages N] [--pdf FILE] [--no-print]
```

Answers, for any PPD: **can ChromeOS add it?** and **will it print?**

| Check | What it does | Needs |
|---|---|---|
| size | ChromeOS refuses PPDs under 200 bytes (gzip is fine) | – |
| cupstestppd | runs `cupstestppd` with ChromeOS's options, plus `-W filters` because this machine lacks ChromeOS's filter programs (filters are checked separately below) | `cupstestppd` (package `cups`) |
| filters | every `cupsFilter`/`cupsFilter2`/`cupsPreFilter` program must be one ChromeOS ships | – |
| ghostscript device | every `-sDEVICE=` in foomatic commands must be in ChromeOS's Ghostscript | – |
| commands | rough scan for programs `foomatic_shell` won't run (the verify step is authoritative) | – |
| foomatic verify | ChromeOS's own add-printer test: `foomatic-rip` in `FOOMATIC_VERIFY_MODE` on ChromeOS's built-in PDF | emulator |
| print run | prints a generated test document (`--pages N`) or your `--pdf` through the emulator; decodes TSPL and ESC/POS output, counts pages, writes a preview PNG | emulator, Ghostscript, Pillow for previews |

Exit status is 0 only if every PPD passed. Jobs, logs and previews go to
`check-out/` (`--out` to change).

## What it can't tell you

- It doesn't run ChromeOS's built-in raster filters (`rastertolabel`,
  `rastertoescpos`, …). For PPDs using them it checks that the filter exists on
  ChromeOS; the print itself needs a Chromebook test.
- USB/network access and the print dialog's behaviour aren't emulated.
- For PostScript-mode PPDs it uses this machine's `pdftops`/`pstops`, not
  ChromeOS's build.
- `chromeos-data.json` reflects ChromeOS as of October 2026. If ChromeOS
  adds or removes filters or Ghostscript devices, update it (sources are noted
  in the file).

## The emulator

Build dependencies on Debian/Ubuntu:

```
sudo apt-get install ghostscript cups cups-filters python3-pil git curl g++ make pkg-config patch \
  libcups2-dev libqpdf-dev liblcms2-dev libfreetype-dev libfontconfig-dev libjpeg-dev \
  libpng-dev libtiff-dev zlib1g-dev libdbus-1-dev libglib2.0-dev
```

`emulator/build.sh` downloads ChromeOS's `foomatic_shell` source
(chromiumos/platform2), ChromeOS's cups-filters patches (chromiumos-overlay)
and cups-filters 1.28.17, then builds both into `emulator/build/` (git-ignored).
`emulator/stub/` and `emulator/fsmain.cc` are small stand-ins written for this
project for the libchrome/brillo pieces `foomatic_shell` needs; parsing and
verification are ChromeOS's own code.
