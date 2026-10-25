#!/usr/bin/env python3
"""Generate a ChromeOS-native PPD from a printer profile (profiles/*.json).

    python3 tools/ppdgen.py profiles/munbyn-rw403b-n.json            > out.ppd
    python3 tools/ppdgen.py --all                                    # writes ppd/*.ppd

Why the PPDs look the way they do (see docs/how-it-works.md):

* ChromeOS runs PPD commands through foomatic_shell, which only allows a few
  programs (printf, gs, sed, cat, cut, date, echo, pdftops), no redirection,
  and no inline PostScript for gs (-c is banned). So every PPD builds the
  printer's job as:  printf <header> ; gs -sDEVICE=bit <1-bit raster> ; printf <footer>

* Ghostscript's "bit" device writes 1 = black.
    - Printer wants 1 = black (most ESC/POS): PDF mode. CUPS hands foomatic-rip
      the PDF; foomatic-rip puts the file path into the FIRST plain "gs" command.
    - Printer wants 0 = black (many TSPL): PostScript mode. CUPS converts with
      pdftops and pstops inserts the "Polarity" option's PostScript, an
      inverting transfer function. gs must then run as a subshell "(gs ...)",
      because foomatic-rip rewrites a bare gs command with -sstdout=%stderr,
      which foomatic_shell rejects.
"""
import argparse
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERSION = "1.0.0"

INVERT_PS = "<</BeginPage{pop{1 exch sub}settransfer}>>setpagedevice"

GS = ("gs -q -dSAFER -dBATCH -dNOPAUSE -dQUIET -sDEVICE=bit -r{dpi} "
      "-g{w}x{h} -dFIXEDMEDIA -dPDFFitPage -dPSFitPage -dFirstPage=1 -dLastPage=1 "
      "-sOutputFile=- -")

TSPL_MEDIA = [
    ("Gap3", "Gap labels (3 mm gap)", "GAP 3.00 mm,0.00 mm"),
    ("Gap2", "Gap labels (2 mm gap)", "GAP 2.00 mm,0.00 mm"),
    ("Gap1", "Gap labels (1 mm gap)", "GAP 1.00 mm,0.00 mm"),
    ("BLine3", "Black mark labels (3 mm mark)", "BLINE 3.00 mm,0.00 mm"),
    ("Continuous", "Continuous roll", "GAP 0.00 mm,0.00 mm"),
]


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def octal(data):
    """bytes -> printf escape text using \\ooo for everything non-printable."""
    out = []
    for b in data:
        c = chr(b)
        if c.isalnum() or c in " ,.:;=+-_/@#()[]{}<>!?*^|~":
            out.append(c)
        else:
            out.append("\\%03o" % b)
    return "".join(out)


def hexbytes(h):
    return bytes.fromhex(h.replace(" ", "")) if h else b""


def wrap(line, width=200):
    """Foomatic treats '&&' + newline inside a string as a continuation, which
    keeps PPD lines under the 255-character limit."""
    if len(line) <= 250 or not line.startswith("*Foomatic"):
        return line
    parts = []
    while len(line) > width:
        cut = line.rfind(" ", 0, width)
        if cut <= 0:
            cut = width
        parts.append(line[:cut] + "&&")
        line = line[cut:]
    parts.append(line)
    return "\n".join(parts)


def size_entries(prof):
    """Normalise profile sizes -> list of (key, label, w_pt, h_pt, default)."""
    out = []
    for s in prof["sizes"]:
        if "width_pt" in s:
            wpt, hpt = float(s["width_pt"]), float(s["height_pt"])
        else:
            wpt = float(s["width_mm"]) / 25.4 * 72
            hpt = float(s["height_mm"]) / 25.4 * 72
        key = s.get("key") or "w%dh%d" % (round(wpt), round(hpt))
        if "label" in s:
            label = s["label"]
        elif "width_mm" in s and prof["language"] == "escpos":
            label = "%g mm x %g mm" % (s["width_mm"], s["height_mm"])
        else:
            label = "%.2fx%.2f in" % (wpt / 72, hpt / 72)
        out.append((key, label, wpt, hpt, bool(s.get("default"))))
    if not any(e[4] for e in out):
        out[0] = out[0][:4] + (True,)
    return out


def dots(points, dpi):
    return int(round(points / 72.0 * dpi))


def nl(s):
    """TSPL line ending as printf escape text."""
    return s + "\\r\\n"


# ----------------------------------------------------------------------------
# language back-ends: each returns (command_line, options) where options is a
# list of PPD option dicts; the PageSize option carries the raster section.
# ----------------------------------------------------------------------------

def gs_cmd(prof, wdots, hdots, ps_mode):
    cmd = GS.format(dpi=prof["dpi"], w=wdots, h=hdots)
    return "(%s)" % cmd if ps_mode else cmd


def backend_tspl(prof, sizes, ps_mode):
    t = prof["tspl"]
    mode = int(t.get("bitmap_mode", 1))
    prefix = "\\r\\n".join(t.get("prefix", ["REFERENCE 0,0", "OFFSET 0"]))
    after = "".join(nl(x) for x in t.get("after_options", ["DIRECTION 0,0"]))
    print_cmd = t.get("print", "PRINT 1,1")
    cmdline = "(printf '%s%%A')" % prefix

    size_settings = []
    for key, label, wpt, hpt, _ in sizes:
        wb = math.ceil(dots(wpt, prof["dpi"]) / 8)
        hd = dots(hpt, prof["dpi"])
        size = "SIZE %.2f mm,%.2f mm" % (wpt / 72 * 25.4, hpt / 72 * 25.4)
        head = "\\r\\n%s%s\\r\\nCLS\\r\\nBITMAP 0,0,%d,%d,%d," % (after, size, wb, hd, mode)
        chunk = "%s'; %s; printf '\\r\\n%s\\r\\n" % (head, gs_cmd(prof, wb * 8, hd, ps_mode),
                                                  print_cmd)
        size_settings.append((key, chunk))

    media = t.get("media_types", [list(m) for m in TSPL_MEDIA])
    dk = t.get("darkness", {"min": 1, "max": 15, "default": 8, "command": "DENSITY {}"})
    sp = t.get("speed", {"min": 1, "max": 8, "default": 4, "command": "SPEED {}"})
    options = [
        dict(name="MediaType", label="Media Type", order=200, spot="A",
             default=t.get("media_default", media[0][0]),
             choices=[(m[0], m[1], "\\r\\n" + m[2]) for m in media]),
        dict(name="Darkness", label="Darkness", order=300, spot="A", default=str(dk["default"]),
             choices=[(str(d), str(d), "\\r\\n" + dk["command"].format(d))
                      for d in range(dk["min"], dk["max"] + 1)]),
        dict(name="PrintSpeed", label="Print Speed", order=400, spot="A",
             default=str(sp["default"]),
             choices=[(str(s), str(s), "\\r\\n" + sp["command"].format(s))
                      for s in range(sp["min"], sp["max"] + 1)]),
    ]
    return cmdline, options, size_settings


def backend_escpos(prof, sizes, ps_mode):
    e = prof["escpos"]
    init = octal(hexbytes(e.get("init_hex", "1b40")))
    cmdline = "(printf '%s%%A%%B')" % init
    max_rows = int(e.get("max_rows", 4095))

    size_settings = []
    for key, label, wpt, hpt, _ in sizes:
        wb = math.ceil(dots(wpt, prof["dpi"]) / 8)
        hd = dots(hpt, prof["dpi"])
        if hd > max_rows:
            raise SystemExit("size %s is %d rows, more than max_rows %d" % (key, hd, max_rows))
        hdr = octal(b"\x1dv0\x00" + bytes([wb & 0xFF, wb >> 8, hd & 0xFF, hd >> 8]))
        chunk = "%s'; %s; printf '" % (hdr, gs_cmd(prof, wb * 8, hd, ps_mode))
        size_settings.append((key, chunk))

    feed_default = int(e.get("feed_lines_default", 4))
    cuts = e.get("cut_hex", {"partial": "1d564200", "full": "1d564100"})
    cut_choices = [("None", "No cut", "")]
    if cuts.get("partial"):
        cut_choices.append(("Partial", "Partial cut", octal(hexbytes(cuts["partial"]))))
    if cuts.get("full"):
        cut_choices.append(("Full", "Full cut", octal(hexbytes(cuts["full"]))))
    options = [
        dict(name="FeedLines", label="Feed before cut (lines)", order=500, spot="B",
             default=str(feed_default),
             choices=[(str(n), str(n), octal(b"\x1bd" + bytes([n])) if n else "")
                      for n in (0, 1, 2, 3, 4, 5, 6, 8, 10)]),
        dict(name="Cut", label="Cut after printing", order=600, spot="B",
             default=e.get("cut_default", "Partial" if cuts.get("partial") else "None"),
             choices=cut_choices),
    ]
    if e.get("drawer_hex"):
        kick = octal(hexbytes(e["drawer_hex"]))
        options.append(dict(name="CashDrawer", label="Open cash drawer", order=100, spot="A",
                            default="None",
                            choices=[("None", "No", ""), ("Before", "Before printing", kick)]))
        options.append(dict(name="CashDrawerAfter", label="Open cash drawer after printing",
                            order=700, spot="B", default="None",
                            choices=[("None", "No", ""), ("After", "After printing", kick)]))
    return cmdline, options, size_settings


BACKENDS = {"tspl": backend_tspl, "escpos": backend_escpos}


# ----------------------------------------------------------------------------

def generate(prof):
    lang = prof["language"]
    if lang not in BACKENDS:
        raise SystemExit("language %r not supported yet" % lang)
    ps_mode = int(prof.get("black_bit", 1)) == 0
    sizes = size_entries(prof)
    default = next(s[0] for s in sizes if s[4])
    cmdline, options, size_settings = BACKENDS[lang](prof, sizes, ps_mode)

    mfg, mdl = prof["manufacturer"], prof["model"]
    nick = "%s %s, %s ChromeOS (chromeos-thermal-ppd %s%s)" % (
        mfg, mdl, lang.upper(), VERSION, ", draft" if prof.get("status") == "draft" else "")
    dev_id = prof.get("ieee1284_id") or "MFG:%s;MDL:%s;" % (mfg, mdl)
    out = []
    w = out.append
    w('*PPD-Adobe: "4.3"')
    w("*% Generated by chromeos-thermal-ppd tools/ppdgen.py from profiles/" + prof["id"] + ".json")
    w("*% Project: chromeos-thermal-ppd. License: GPL-3.0-or-later.")
    w("*% Status: " + prof.get("status", "draft") + ". Profile notes:")
    for note in prof.get("notes", []):
        w("*%   " + note)
    w("*% Runs only printf + Ghostscript, as allowed by ChromeOS foomatic_shell.")
    w('*FormatVersion: "4.3"')
    w('*FileVersion: "%s"' % VERSION)
    w("*LanguageVersion: English")
    w("*LanguageEncoding: ISOLatin1")
    w('*PCFileName: "%s.PPD"' % prof["id"][:8].upper())
    w('*Manufacturer: "%s"' % mfg)
    w('*Product: "(%s)"' % mdl)
    w('*ModelName: "%s %s"' % (mfg, mdl))
    w('*ShortNickName: "%s %s"' % (mfg, mdl))
    w('*NickName: "%s"' % nick)
    w('*1284DeviceID: "%s"' % dev_id)
    w('*PSVersion: "(3010.000) 0"')
    w('*LanguageLevel: "3"')
    w("*ColorDevice: False")
    w("*DefaultColorSpace: Gray")
    w("*FileSystem: False")
    w('*Throughput: "1"')
    w("*LandscapeOrientation: Plus90")
    w("*TTRasterizer: Type42")
    w("*cupsVersion: 2.2")
    w("*cupsManualCopies: True")
    if ps_mode:
        w('*cupsFilter: "application/vnd.cups-postscript 0 foomatic-rip"')
    else:
        w('*cupsFilter: "application/vnd.cups-pdf 0 foomatic-rip"')
        w('*cupsFilter: "application/vnd.cups-postscript 100 foomatic-rip"')
    w("*FoomaticIDs: %s %s" % (prof["id"], lang))
    w('*FoomaticRIPCommandLine: "%s"' % cmdline)
    if not ps_mode:
        w('*FoomaticRIPCommandLinePDF: "%s"' % cmdline)
    w("*HWMargins: 0 0 0 0")
    w("")

    w("*OpenUI *PageSize/Media Size: PickOne")
    w("*FoomaticRIPOption PageSize: enum CmdLine A")
    w("*OrderDependency: 900 AnySetup *PageSize")
    w("*DefaultPageSize: %s" % default)
    for key, label, wpt, hpt, _ in sizes:
        w('*PageSize %s/%s: "<</PageSize[%g %g]/ImagingBBox null>>setpagedevice"'
          % (key, label, round(wpt, 2), round(hpt, 2)))
    for key, chunk in size_settings:
        w('*FoomaticRIPOptionSetting PageSize=%s: "%s"' % (key, chunk))
    w("*CloseUI: *PageSize")
    w("")
    w("*OpenUI *PageRegion/Media Size: PickOne")
    w("*OrderDependency: 900 AnySetup *PageRegion")
    w("*DefaultPageRegion: %s" % default)
    for key, label, wpt, hpt, _ in sizes:
        w('*PageRegion %s/%s: "<</PageSize[%g %g]/ImagingBBox null>>setpagedevice"'
          % (key, label, round(wpt, 2), round(hpt, 2)))
    w("*CloseUI: *PageRegion")
    w("")
    w("*DefaultImageableArea: %s" % default)
    for key, label, wpt, hpt, _ in sizes:
        w('*ImageableArea %s/%s: "0 0 %g %g"' % (key, label, round(wpt, 2), round(hpt, 2)))
    w("*DefaultPaperDimension: %s" % default)
    for key, label, wpt, hpt, _ in sizes:
        w('*PaperDimension %s/%s: "%g %g"' % (key, label, round(wpt, 2), round(hpt, 2)))
    w("")
    w("*OpenUI *Resolution/Resolution: PickOne")
    w("*OrderDependency: 100 AnySetup *Resolution")
    w("*DefaultResolution: %ddpi" % prof["dpi"])
    w('*Resolution %ddpi/%d dpi: ""' % (prof["dpi"], prof["dpi"]))
    w("*CloseUI: *Resolution")
    w("")
    if ps_mode:
        w("*OpenUI *Polarity/Image Polarity: PickOne")
        w("*OrderDependency: 50 AnySetup *Polarity")
        w("*DefaultPolarity: Printer")
        w('*Polarity Printer/Normal (printer wants 0 = black): "%s"' % INVERT_PS)
        w('*Polarity Raw/Inverted (diagnostic only): ""')
        w("*CloseUI: *Polarity")
        w("")
    for o in options:
        w("*OpenUI *%s/%s: PickOne" % (o["name"], o["label"]))
        w("*FoomaticRIPOption %s: enum CmdLine %s" % (o["name"], o["spot"]))
        w("*OrderDependency: %d AnySetup *%s" % (o["order"], o["name"]))
        w("*Default%s: %s" % (o["name"], o["default"]))
        for key, label, val in o["choices"]:
            w('*%s %s/%s: ""' % (o["name"], key, label))
            w('*FoomaticRIPOptionSetting %s=%s: "%s"' % (o["name"], key, val))
        w("*CloseUI: *%s" % o["name"])
        w("")
    w("*DefaultFont: Courier")
    w('*Font Courier: Standard "(002.004S)" Standard ROM')
    w("*% End of PPD")
    return "\n".join(wrap(l) for l in out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile", nargs="?", help="profile JSON file")
    ap.add_argument("--all", action="store_true",
                    help="generate ppd/<id>.ppd for every profiles/*.json")
    args = ap.parse_args()
    if args.all:
        os.makedirs(os.path.join(ROOT, "ppd"), exist_ok=True)
        for path in sorted(glob.glob(os.path.join(ROOT, "profiles", "*.json"))):
            prof = json.load(open(path))
            dest = os.path.join(ROOT, "ppd", prof["id"] + ".ppd")
            with open(dest, "w") as f:
                f.write(generate(prof))
            print("wrote", os.path.relpath(dest, ROOT))
        return
    if not args.profile:
        ap.error("give a profile file or --all")
    sys.stdout.write(generate(json.load(open(args.profile))))


if __name__ == "__main__":
    main()
