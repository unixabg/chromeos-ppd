# chromeos-thermal-ppd

ChromeOS-native drivers (PPD files) for thermal label and receipt printers:
**no browser extension, no vendor software, no print server.** The PPDs work in
regular ChromeOS sessions, in managed guest sessions, and can be pushed to
ChromeOS devices from the Google Admin console. They also work with CUPS on
Linux.

> Not affiliated with any printer manufacturer. Trademarks belong to their owners.

## Supported printers

| Printer | Language | Connection tested | Status | PPD |
|---|---|---|---|---|
| Munbyn RW403B-N | TSPL | USB | ✅ Tested on ChromeOS (managed guest session) and Linux CUPS (v1.0); multi-page v1.1 retest pending | [`ppd/munbyn-rw403b-n.ppd`](ppd/munbyn-rw403b-n.ppd) |
| Rongta RP850P (80 mm) | ESC/POS | USB | ✅ Tested on ChromeOS (multi-page, v1.1) and Linux CUPS | [`ppd/rongta-rp850p.ppd`](ppd/rongta-rp850p.ppd) |

Your printer not listed? See [Adding a printer](docs/adding-a-printer.md). It
takes about 15 minutes with a Linux machine and the printer.

## Using a PPD

**Chromebook (regular login):** Settings → Advanced → Print and scan →
Printers → set up the printer → "specify your printer PPD" → choose the file.

**Managed ChromeOS devices / managed guest sessions / kiosks:** see
[docs/chromeos-admin-console.md](docs/chromeos-admin-console.md). In short:
host the PPD on HTTPS, then in the Admin console add the printer with
Connection **USB** (vendor + product ID) or **Network address**, Setup method
**Custom PPD file**, and allow it for your org unit.

**Linux (CUPS):**
```
sudo lpadmin -p RW403B -E -v 'usb://Munbyn/RW403B-N?serial=…' -P ppd/munbyn-rw403b-n.ppd
```

When printing, pick the paper size that matches your labels or receipt length
and set margins to none.

## How it works

ChromeOS won't run vendor driver programs. It does run PPD commands through a
locked-down shell (`foomatic_shell`) that allows `printf` and Ghostscript.
Every PPD here builds the printer's whole job with a single Ghostscript run:

```
gs -sDEVICE=uniprint  + the printer's own bytes before/after the job and every page
```

Ghostscript's `uniprint` device writes a custom header before each page's raw
1-bit image and a custom footer after it, so every page of a document prints
(a label each, or one continuous receipt), in either bitmap polarity.

The details (polarity, PDF vs PostScript mode, and the ChromeOS traps) are in
[docs/how-it-works.md](docs/how-it-works.md).

## Repository layout

```
profiles/      one JSON file per printer: language, polarity, commands, sizes
ppd/           generated PPDs (make ppds)
tools/
  probe.py     sends numbered test prints, writes a draft profile from your answers
  ppdgen.py    profile -> PPD
  preview.py   renders a printer job (TSPL/ESC/POS) to PNG
  bitmap.py    test-image helper
tests/chromeos/  rebuilds ChromeOS's print sandbox locally and runs every PPD through it
docs/          how it works, adding a printer, Admin console setup
```

```
make ppds        # regenerate PPDs from profiles
make check       # cupstestppd
make emulator    # build the ChromeOS emulator (once; downloads sources)
make test        # run every PPD through the ChromeOS emulator
```

## Limitations

- Fixed page sizes per printer (listed in its profile). For receipts, choose a
  length that fits your content; shorter is less paper.
- Languages: TSPL and ESC/POS today. ZPL, EPL and CPCL should work the same
  way and are welcome contributions. Printers whose raster format needs extra
  data on every row (Brother QL, DYMO LabelWriter) can't be driven with the
  tools ChromeOS allows.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE). Contributions are accepted under the
same license (see [CONTRIBUTING.md](CONTRIBUTING.md)).
