# chromeos-ppd

Printer drivers (PPD files) that work on **ChromeOS**, and a tool that tells
you whether **any** PPD will.

ChromeOS can't install vendor driver software. A printer that ChromeOS doesn't
set up by itself needs a PPD built from what ChromeOS already has: its CUPS
filters, its Ghostscript, and a locked-down shell. This project collects such
PPDs, the tools to make them, and a checker that tests a PPD against
ChromeOS's real rules without needing a Chromebook.

> Not affiliated with Google or any printer manufacturer. Trademarks belong to their owners.

## 1. Printers

| Printer | Family | Connection tested | Status | PPD |
|---|---|---|---|---|
| Munbyn RW403B-N | thermal (TSPL labels) | USB | ✅ ChromeOS (managed guest session) and Linux CUPS (v1.0); multi-page v1.1 retest pending | [`ppd/munbyn-rw403b-n.ppd`](ppd/munbyn-rw403b-n.ppd) |
| Rongta RP850P (80 mm) | thermal (ESC/POS receipts) | USB | ✅ ChromeOS (multi-page, v1.1) and Linux CUPS | [`ppd/rongta-rp850p.ppd`](ppd/rongta-rp850p.ppd) |

PPDs are grouped by **family**, a kind of printer that shares one approach and
one set of tools. See [families/](families/README.md). Your printer isn't
listed? Run the checker on its vendor PPD first, then see
[CONTRIBUTING.md](CONTRIBUTING.md).

### Using a PPD

- **Chromebook:** Settings → Advanced → Print and scan → Printers → set up the
  printer → "specify your printer PPD" → choose the file.
- **Managed devices, managed guest sessions, kiosks:** push it from the Google
  Admin console. See [docs/chromeos-admin-console.md](docs/chromeos-admin-console.md).
- **Linux:** `sudo lpadmin -p NAME -E -v '<uri from lpinfo -v>' -P ppd/<file>.ppd`

## 2. The checker: will this PPD work on ChromeOS?

```
bash checker/emulator/build.sh                      # once: builds ChromeOS's print sandbox
python3 checker/chromeos_ppd_check.py some-printer.ppd
```

It works on any PPD: a vendor's, one from this repository, or one you wrote.
It answers two questions, **can ChromeOS add it?** and **will it print?**, by:

- running **ChromeOS's own add-printer test** exactly as ChromeOS does
  (`cupstestppd` with ChromeOS's options, then `foomatic-rip` in verify mode);
- checking every **filter** the PPD needs against the filters ChromeOS ships,
  including the third-party ones (DYMO, Star, Epson, TSC, generic ESC/POS, HP,
  Canon, …), and every **Ghostscript device** against ChromeOS's build;
- **printing** a test document through ChromeOS's real `foomatic_shell` and
  ChromeOS-patched `foomatic-rip`, and decoding the output where it can.

```
=== vendor.ppd
  FAIL  filters   application/pdf -> /Library/Printers/Acme/pdf_to_tspl: a vendor program;
                  ChromeOS can't install it, so it refuses the PPD (missing filter)
  ---- ChromeOS can add it: NO.  Expected to print: NO.
```

Details: [checker/README.md](checker/README.md). What ChromeOS allows and why:
[docs/chromeos-printing.md](docs/chromeos-printing.md).

## Repository layout

```
ppd/                    all PPDs, any family
families/<family>/      tools and sources for one kind of printer (thermal: profiles, generator, probe)
checker/                chromeos_ppd_check.py, chromeos-data.json (what ChromeOS ships), emulator/
docs/                   ChromeOS printing rules, Admin console deployment
samples/                test documents
```

```
make ppds        # regenerate generated PPDs (every family)
make emulator    # build the ChromeOS sandbox for the checker (once; downloads sources)
make check       # run the checker on every PPD in ppd/, with a 2-page document
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE). Contributions are accepted under the
same license (see [CONTRIBUTING.md](CONTRIBUTING.md)).
