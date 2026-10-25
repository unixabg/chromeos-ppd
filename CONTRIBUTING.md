# Contributing

Thanks for helping more printers work on ChromeOS. The most useful
contributions are:

- **A checker report** on a vendor PPD (`python3 checker/chromeos_ppd_check.py vendor.ppd`):
  open an issue with the output, so others know whether that printer can work.

- **A new thermal printer:** follow [families/thermal/adding-a-printer.md](families/thermal/adding-a-printer.md).
- **A PPD for another kind of printer, or a new family:** see [families/README.md](families/README.md).
- **Checker data:** ChromeOS adds or drops a filter or Ghostscript device? Update
  `checker/chromeos-data.json` and say where you found it.
- **A test report:** you used an existing PPD. Open an issue saying what
  worked or didn't, with printer model, connection (USB/network), ChromeOS
  version and session type (regular / managed guest / kiosk) or Linux CUPS
  version. A photo of the printout helps.
- **A new thermal language** (ZPL, EPL, CPCL, …): see the end of the thermal adding guide.

## Ground rules

- **Don't add vendor files.** No vendor PPDs, driver programs, installers,
  firmware or manuals, even if they're freely downloadable. They aren't
  ours to relicense. Describe what you learned (commands, quirks) in the
  profile's `notes` instead, and link to the vendor's download page if useful.
- **Generated PPDs are generated.** For a family with a generator (thermal), edit
  its profiles or generator and run `make ppds`; don't hand-edit those PPDs.
  Hand-written PPDs are welcome where a family has no generator.
- **Keep `"status": "draft"`** until someone has printed from a Chromebook with it.
- **Every PPD in `ppd/` must pass `make check`** (the ChromeOS checker).
- Python: standard library only for the probe, generators and checker, so they
  run on any machine. Previews may use Pillow.

## License

By contributing you agree that your contribution is licensed under
GPL-3.0-or-later, the same as the rest of the project.
