# How it works

## The constraint

ChromeOS's print system is CUPS, but locked down:

- Vendor filter programs can't be installed or run.
- `foomatic-rip` (from cups-filters 1.28.17) is available, and it runs a PPD's
  commands through **`foomatic_shell`**, ChromeOS's restricted shell
  (chromiumos/platform2). It allows only `cat`, `cut`, `date`, `echo`, `gs`,
  `pdftops`, `printf` and `sed`, supports `;`, `|`, `( )` and quoting, and has
  **no redirection** (`<`, `>`). Unquoted arguments may only contain letters,
  digits and `. / _ - + @ %`; anything else must be in single quotes.
- `gs` must have `-dSAFER` and `-sOutputFile=-`, may read only stdin or files in
  `/tmp/` and `/var/spool/cups/`, and may not use `-c`, `-o`, `@file`, `NOSAFER`,
  `OutputFile`, `OutputICCProfile` or **`stdout`**.
- ChromeOS's Ghostscript is built with a fixed device list. It includes
  `uniprint` and `bit`.

## The recipe: Ghostscript's `uniprint` device (engine `uniprint`, default)

`uniprint` is a configurable raster device. Given a **non-empty**
`upBeginPageCommand`, it writes:

```
upBeginJobCommand
for every page:  upBeginPageCommand  +  raw 1-bit rows (MSB first)  +  upEndPageCommand
upEndJobCommand
```

with no header of its own. That's exactly the shape of a thermal printer job,
so each PPD is a single `gs` command whose `-dup…Command=<hex>` arguments hold
the printer's bytes:

| | TSPL label printer | ESC/POS receipt printer |
|---|---|---|
| job start | – | `ESC @` (+ cash drawer) |
| page start | `REFERENCE`, `OFFSET`, `GAP`, `DENSITY`, `SPEED`, `DIRECTION`, `SIZE`, `CLS`, `BITMAP 0,0,w,h,1,` | `GS v 0 0 xL xH yL yH` |
| page end | `PRINT 1,1` | optional feed + cut ("Cut between pages") |
| job end | – | feed + cut (+ cash drawer) |

Options (label size, darkness, cut, …) are ordinary foomatic options whose
values are hex pasted into those arguments. The PageSize option comes last: it
finishes the page-start bytes, closes the argument and adds the matching
`-gWIDTHxHEIGHT`.

Details that matter:

- **Polarity.** `uniprint`'s native output is **0 = black** (TSPL's usual
  convention). `'-dupWhiteTransfer={1.0 0.0}'` flips it to **1 = black**
  (ESC/POS). The generator adds it when the profile says `"black_bit": 1`.
- **Row padding.** Rows are padded to an even number of bytes, so the raster
  width is rounded up to a multiple of 16 dots and that width is declared to
  the printer.
- **Never empty.** With an empty `upBeginPageCommand`, `uniprint` writes a Sun
  raster header instead. Every language has a page-start command, so this
  doesn't happen.
- **PDF mode.** CUPS hands `foomatic-rip` the PDF and `foomatic-rip` inserts
  the file path into the `gs` command. The command must start with a bare
  `gs` for that to work.

## The older engine: `bit` (single page)

Before `uniprint`, the PPDs used `printf '<header>'; gs -sDEVICE=bit; printf
'<footer>'`. It still works and stays available (`"engine": "bit"` in a
profile), but it can only print **the first page**, because the header must
state the image height before the image and one `gs` run outputs all pages
back to back. For 0 = black printers it also needs PostScript mode: an inverting
`settransfer` inserted by CUPS's `pstops`, and `gs` run as a subshell
`(gs …)`, because `foomatic-rip` otherwise adds `-sstdout=%stderr`, which
ChromeOS rejects.

## Printer firmware quirks

Cheap thermal printers often implement only part of their language and
silently drop a whole job when they see something they don't like. The Munbyn
RW403B-N, for example, rejects `BITMAP` mode 0 and mode 2 and ignores `TEXT`,
`BAR` and `REVERSE`. That's why every profile is based on probe results from
the real printer, not on the language manual.

## Testing without a Chromebook

The [checker](../../checker/README.md) builds ChromeOS's real `foomatic_shell` and a ChromeOS-patched
`foomatic-rip` and runs each PPD through them, including multi-page documents
(`--pages N`). It reports the same errors ChromeOS would ("gs: disallowed
name", parse errors), checks the bitmap sizes decode, counts the pages and
flags inverted output.
