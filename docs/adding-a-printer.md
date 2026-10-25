# Adding a printer

You need: the printer, labels or paper loaded, and a Linux machine with
Python 3, CUPS and Ghostscript. A Chromebook is only needed for the final test.

## 1. Identify it

Plug the printer in by USB and run:

```
sudo python3 tools/probe.py --list
```

This shows the device file (`/dev/usb/lp0`), USB vendor/product ID and the
printer's own device ID, for example `MFG:Munbyn;CMD:TSPL;MDL:RW403B-N;`. The
`CMD:` part tells you the language. `tools/probe.py` supports `tspl` and
`escpos`. For other languages, see "New languages" below.

Network printers: use `--device socket://IP:9100 --language …`.
Serial: `--device /dev/ttyUSB0 --baud 19200 --language …`.

## 2. Run the probe

```
# TSPL label printer: give the label size, width x length in inches
sudo python3 tools/probe.py --size 3x2

# ESC/POS receipt printer: give the printable width in dots
# (576 for 80 mm paper, 384 for 58 mm). --drawer also tests a cash drawer.
sudo python3 tools/probe.py --dots 576 --drawer
```

Each test print shows its number as small squares top-left and large digits
top-right. After each one, answer **normal**, **inverted** (white on black),
**nothing**, or describe it. For the ESC/POS cut test, list the letters that
were followed by a cut, e.g. `B D`.

If the printer stops responding (some firmware hangs on a test it dislikes),
power-cycle it and rerun from the next test with `--only N`.

The probe writes a draft profile, `probe-<model>.json`.

## 3. Turn it into a profile

Copy the draft to `profiles/<maker>-<model>.json` and check it:

- `id`, `manufacturer`, `model`: tidy names.
- `black_bit`: 0 or 1, from the polarity tests.
- `sizes`: the labels/receipt lengths people will use. Mark one `"default": true`.
- `usb.vid` / `usb.pid`: needed for the Admin console.
- Keep `"status": "draft"` until it has printed from a Chromebook.

See `profiles/munbyn-rw403b-n.json` (TSPL) and `profiles/rongta-rp850p.json`
(ESC/POS) for complete examples.

## 4. Generate and test

```
make ppds           # writes ppd/<id>.ppd
make check          # cupstestppd
make emulator       # once
make test           # ChromeOS emulator: must say PASS
```

Then on Linux, print through it for real:

```
sudo lpadmin -p TEST -E -v '<usb uri from lpinfo -v>' -P ppd/<id>.ppd
lp -d TEST tests/out/<id>-test.pdf
```

Finally on a Chromebook: set the printer up with the PPD and print a page.

## 5. Open a pull request

Include the profile, the generated PPD, a line for the README table, and
what you tested on (ChromeOS version/session type, Linux CUPS version,
connection). A photo of a test print helps.

## New languages (ZPL, EPL, CPCL, …)

The approach works for any language that takes a raster image as one block,
with fixed bytes before and after. To add one:

1. `tools/probe.py`: add a test suite (see `tspl_suite` / `escpos_suite`):
   polarity both ways, the bitmap command variants, and anything the language
   needs to finish a job (form feed, cut).
2. `tools/ppdgen.py`: add a back-end (see `backend_tspl` / `backend_escpos`)
   that returns the command line, the options and, per page size, the raster
   header + `gs` + footer chunk.
3. `tools/preview.py`: teach it to draw the new bitmap command.

Useful starting points: ZPL `^GFB` (binary graphic field, 1 = black), EPL
`GW`, CPCL `EG`.
