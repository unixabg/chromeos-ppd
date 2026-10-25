# ChromeOS print-pipeline emulator

ChromeOS runs PPD commands through `foomatic_shell`, a restricted shell that
only allows a few programs and rejects anything else. These scripts rebuild
that environment on a normal Linux machine so a PPD can be checked before it
goes near a Chromebook.

- `build.sh` downloads ChromeOS's `foomatic_shell` source (chromiumos/platform2),
  ChromeOS's cups-filters patches (chromiumos-overlay) and cups-filters 1.28.17,
  then builds both. Nothing downloaded is stored in this repository.
- `stub/` and `fsmain.cc` are small stand-ins written for this project for the
  parts of libchrome/brillo that `foomatic_shell` needs (process launching,
  temp files, logging). They don't change how scripts are parsed or verified;
  that code is ChromeOS's own.
- `emulate.py` prints a test page through each PPD and checks the result.

What it doesn't cover: ChromeOS's USB/network access, the print dialog, and
the exact `pdftops` build (your system's `pdftops` + `pstops` is used for
PostScript-mode PPDs). A Chromebook test is still the final word.
