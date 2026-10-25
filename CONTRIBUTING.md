# Contributing

Thanks for helping more printers work on ChromeOS. The most useful
contributions are:

- **A new printer profile:** follow [docs/adding-a-printer.md](docs/adding-a-printer.md).
- **A test report:** you used an existing PPD. Open an issue saying what
  worked or didn't, with printer model, connection (USB/network), ChromeOS
  version and session type (regular / managed guest / kiosk) or Linux CUPS
  version. A photo of the printout helps.
- **A new printer language** (ZPL, EPL, CPCL, …): see the end of the adding guide.

## Ground rules

- **Don't add vendor files.** No vendor PPDs, driver programs, installers,
  firmware or manuals, even if they're freely downloadable. They aren't
  ours to relicense. Describe what you learned (commands, quirks) in the
  profile's `notes` instead, and link to the vendor's download page if useful.
- **PPDs are generated.** Edit `profiles/*.json` or `tools/ppdgen.py`, then run
  `make ppds`. Don't hand-edit `ppd/`.
- **Keep `"status": "draft"`** until someone has printed from a Chromebook with it.
- **`make test` must pass** (ChromeOS emulator) before a PPD is merged.
- Python: standard library only for `probe.py`/`ppdgen.py`, so they run on
  any machine. `preview.py` may use Pillow.

## License

By contributing you agree that your contribution is licensed under
GPL-3.0-or-later, the same as the rest of the project.
