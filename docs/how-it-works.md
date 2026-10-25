# How it works

## The constraint

ChromeOS's print system is CUPS, but locked down:

- Vendor filter programs can't be installed or run.
- `foomatic-rip` (from cups-filters 1.28.17) is available, and it runs a PPD's
  commands through **`foomatic_shell`**, ChromeOS's restricted shell
  (chromiumos/platform2). It allows only `cat`, `cut`, `date`, `echo`, `gs`,
  `pdftops`, `printf` and `sed`, supports `;`, `|`, `( )` and quoting, and has
  **no redirection** (`<`, `>`).
- `gs` must have `-dSAFER` and `-sOutputFile=-`, may read only stdin or files in
  `/tmp/` and `/var/spool/cups/`, and may not use `-c`, `-o`, `@file`, `NOSAFER`,
  `OutputFile`, `OutputICCProfile` or **`stdout`**.
- ChromeOS's Ghostscript includes the raw `bit` device.

## The recipe

Ghostscript renders the page to a raw 1-bit image (`-sDEVICE=bit`, one row
after another, MSB first). Most thermal printers accept exactly that inside a
single bitmap command, so the PPD only has to put the printer's own commands
before and after it:

```
(printf 'HEADER…BITMAP x,y,w,h,mode,' ; gs -sDEVICE=bit -r203 -gWxH … ; printf 'FOOTER')
```

Options (label size, darkness, cut, cash drawer, …) are ordinary foomatic
options whose values are pasted into those `printf` strings.

## Polarity: 1 = black or 0 = black?

Ghostscript's `bit` device writes **1 = black**. Printers disagree:

- **Printer wants 1 = black** (ESC/POS `GS v 0`, many others) → **PDF mode.**
  CUPS hands `foomatic-rip` the PDF. `foomatic-rip` adds the file path to the
  first plain `gs` command it finds.
- **Printer wants 0 = black** (e.g. Munbyn RW403B-N TSPL) → **PostScript mode.**
  The image has to be inverted, and nothing allowed can invert bytes reliably
  (`sed y///` corrupts binary data under a UTF-8 locale). Instead the PPD has a
  PostScript option, *Image Polarity*, whose code is
  `<</BeginPage{pop{1 exch sub}settransfer}>>setpagedevice`. The PPD accepts
  only PostScript, so CUPS converts with `pdftops`, and `pstops` inserts that
  code into the job. Ghostscript then renders a negative, which is 0 = black.

## Two foomatic-rip traps

1. **PostScript mode rewrites `gs`.** `foomatic-rip` adds `-sstdout=%stderr` to
   any command that starts with `gs`, and ChromeOS rejects the name `stdout`.
   Fix: run it in a subshell, `(gs …)`. The command then starts with `(`, so
   `foomatic-rip` leaves it alone.
2. **PDF mode needs a bare `gs`.** `foomatic-rip` inserts the PDF file path into
   the first `gs` it finds. If there's none (for example because it's wrapped
   in `( )`), it appends `< file` instead, which `foomatic_shell` can't parse.
   So in PDF mode `gs` must not be wrapped.

`tools/ppdgen.py` picks the right mode from the profile's `black_bit`.

## Printer firmware quirks

Cheap thermal printers often implement only part of their language and
silently drop a whole job when they see something they don't like. The Munbyn
RW403B-N, for example, rejects `BITMAP` mode 0 and mode 2 and ignores `TEXT`,
`BAR` and `REVERSE`. That's why every profile is based on probe results from
the real printer, not on the language manual.

## Testing without a Chromebook

`tests/chromeos/` builds ChromeOS's real `foomatic_shell` and a ChromeOS-patched
`foomatic-rip` and runs each PPD through them. It catches every problem above
(it reports the same "gs: disallowed name" error ChromeOS would, and flags
inverted output).
