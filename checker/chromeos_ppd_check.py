#!/usr/bin/env python3
"""chromeos-ppd-check: will this PPD install and print on ChromeOS?

    python3 checker/chromeos_ppd_check.py some-printer.ppd [more.ppd ...]
    python3 checker/chromeos_ppd_check.py ppd/*.ppd --pages 2
    python3 checker/chromeos_ppd_check.py vendor.ppd --pdf my-document.pdf

Works for any PPD: vendor PPDs, PPDs from this repository, OpenPrinting PPDs.

Checks, in order:

  1. ChromeOS's own add-printer test, exactly as debugd runs it:
     size >= 200 bytes (gzip allowed), `cupstestppd -W translations -W
     constraints` must pass, and for foomatic PPDs `foomatic-rip` must pass
     in FOOMATIC_VERIFY_MODE on ChromeOS's tiny built-in PDF.
  2. Filters: every filter the PPD needs must be one ChromeOS ships.
     Vendor programs (e.g. /Library/Printers/... or a custom rastertoXXX)
     can't be installed on ChromeOS.
  3. Ghostscript devices named in foomatic commands must be in ChromeOS's
     Ghostscript build.
  4. Print run (foomatic PPDs): a test document (or --pdf) goes through the
     ChromeOS-patched foomatic-rip and ChromeOS's foomatic_shell. TSPL and
     ESC/POS output is decoded, pages counted and previews written.

Steps 1 (verify mode) and 4 need the emulator: `bash checker/emulator/build.sh`
(once). Without it those steps are skipped and the rest still runs.

Exit status: 0 if every PPD passed, 1 otherwise.
"""
import argparse
import glob
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = json.load(open(os.path.join(HERE, "chromeos-data.json")))
BUILD = os.path.join(HERE, "emulator", "build")
FOOMATIC_RIP = os.path.join(BUILD, "cups-filters", "foomatic-rip")
PDFTOPS = next((p for p in ("/usr/lib/cups/filter/pdftops",
                            "/usr/libexec/cups/filter/pdftops") if os.path.exists(p)), None)
sys.path.insert(0, os.path.join(ROOT, "families", "thermal"))

PASS, WARN, FAIL, SKIP, INFO = "PASS", "WARN", "FAIL", "SKIP", "INFO"


class Report:
    def __init__(self, name):
        self.name = name
        self.items = []

    def add(self, level, check, msg):
        self.items.append((level, check, msg))

    @property
    def failed(self):
        return any(l == FAIL for l, _, _ in self.items)

    def show(self):
        print("\n=== %s" % self.name)
        for level, check, msg in self.items:
            print("  %-4s  %-22s %s" % (level, check, msg))
        # A filter ChromeOS doesn't have also blocks adding: ChromeOS runs
        # cupstestppd without -W filters, and the missing file is an error.
        install = not any(l == FAIL and c in ("size", "cupstestppd", "foomatic verify", "filters")
                          for l, c, _ in self.items)
        prints = not self.failed
        print("  ---- ChromeOS can add it: %s.  Expected to print: %s." % (
            "yes" if install else "NO", "yes" if prints else "NO"))


# ----------------------------------------------------------------------------
# PPD parsing
# ----------------------------------------------------------------------------

def read_ppd(path):
    raw = open(path, "rb").read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def ppd_values(text, keyword):
    """All values of *keyword (handles quoted values and foomatic &&-continuations)."""
    out = []
    for m in re.finditer(r'^\*%s(?:\s+[^:]*)?:\s*"(.*?)"' % re.escape(keyword), text, re.M | re.S):
        out.append(m.group(1).replace("&&\n", ""))
    return out


def filters_of(text):
    """(mime source, program) for cupsFilter / cupsFilter2 / cupsPreFilter."""
    out = []
    for kw in ("cupsFilter", "cupsFilter2", "cupsPreFilter"):
        for v in ppd_values(text, kw):
            parts = v.split()
            if kw == "cupsFilter2" and len(parts) >= 4:
                out.append((parts[0], " ".join(parts[3:])))
            elif len(parts) >= 3:
                out.append((parts[0], " ".join(parts[2:])))
    return out


def unhtml(s):
    return (s.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
            .replace("&amp;", "&"))


# ----------------------------------------------------------------------------
# checks
# ----------------------------------------------------------------------------

def check_size(rep, raw):
    if len(raw) < DATA["add_printer_check"]["min_size"]:
        rep.add(FAIL, "size", "%d bytes; ChromeOS rejects PPDs under 200 bytes" % len(raw))
    else:
        rep.add(PASS, "size", "%d bytes" % len(raw))


def check_cupstestppd(rep, raw):
    exe = shutil.which("cupstestppd")
    if not exe:
        rep.add(SKIP, "cupstestppd", "cupstestppd not installed (package: cups)")
        return
    # ChromeOS's arguments, plus "-W filters": this machine doesn't have
    # ChromeOS's filter programs installed, so missing-filter errors would be
    # false alarms. Filters are checked against ChromeOS's list separately.
    args = DATA["add_printer_check"]["cupstestppd_args"][:-1] + ["-W", "filters", "-"]
    r = subprocess.run([exe] + args, input=raw, capture_output=True)
    out = r.stdout.decode(errors="replace")
    if r.returncode == 0:
        warns = [l.strip() for l in out.splitlines() if l.strip().startswith("WARN")]
        rep.add(PASS, "cupstestppd", "passes as ChromeOS runs it"
                + (" (%d warnings)" % len(warns) if warns else ""))
    else:
        fails = [l.strip().replace("**FAIL**", "").strip() for l in out.splitlines()
                 if "**FAIL**" in l][:3]
        rep.add(FAIL, "cupstestppd", "ChromeOS would refuse to add it: "
                + ("; ".join(fails) or out.strip().splitlines()[-1]))


def check_filters(rep, text):
    known = DATA["filters"]
    flist = filters_of(text)
    if not flist:
        rep.add(PASS, "filters", "no filters (driverless/PostScript path)")
        return []
    names = []
    for src, prog in flist:
        name = os.path.basename(prog)
        names.append(name)
        if prog == "-":
            rep.add(PASS, "filters", "%s: passed through unchanged" % src)
            continue
        if prog.startswith("/") and os.path.dirname(prog) not in (
                "/usr/libexec/cups/filter", "/usr/lib/cups/filter"):
            rep.add(FAIL, "filters", "%s -> %s: a vendor program; ChromeOS can't install it, "
                    "so it refuses the PPD (missing filter)" % (src, prog))
            continue
        if name in known:
            rep.add(PASS, "filters", "%s -> %s (ChromeOS: %s, %s)" % (
                src, name, known[name]["package"], known[name]["for"]))
            continue
        pat = next((p for p in DATA["filter_name_patterns"] if re.match(p, name)), None)
        if pat:
            rep.add(WARN, "filters", "%s -> %s: %s" % (src, name, DATA["filter_name_patterns"][pat]))
        else:
            rep.add(FAIL, "filters", "%s -> %s: not a filter ChromeOS ships, so ChromeOS "
                    "refuses the PPD (see checker/chromeos-data.json)" % (src, name))
    return names


def check_gs_devices(rep, text):
    strings = [unhtml(v) for kw in ("FoomaticRIPCommandLine", "FoomaticRIPCommandLinePDF",
                                    "FoomaticRIPOptionSetting") for v in ppd_values(text, kw)]
    devices = sorted(set(re.findall(r"-sDEVICE=([A-Za-z0-9_.-]+)", " ".join(strings))))
    for d in devices:
        if d in DATA["ghostscript_devices"]:
            rep.add(PASS, "ghostscript device", "%s is in ChromeOS's Ghostscript" % d)
        else:
            rep.add(FAIL, "ghostscript device", "%s is NOT in ChromeOS's Ghostscript build" % d)
    # Rough static scan for programs foomatic_shell won't run. The verify-mode
    # run below is authoritative; this only helps when the emulator isn't built.
    allowed = set(DATA["foomatic_shell_commands"])
    cmdlines = [unhtml(v) for kw in ("FoomaticRIPCommandLine", "FoomaticRIPCommandLinePDF")
                for v in ppd_values(text, kw)]
    settings = [unhtml(v) for v in ppd_values(text, "FoomaticRIPOptionSetting")]
    seen = set()
    for s, at_start in [(c, True) for c in cmdlines] + [(o, False) for o in settings]:
        s = re.sub(r"'[^']*'", "''", s)              # drop quoted text
        lead = r"(?:^|[;|(`])" if at_start else r"[;|(`]"
        for word in re.findall(lead + r"\s*([A-Za-z][A-Za-z0-9_./-]*)", s):
            if word not in allowed and word not in seen:
                seen.add(word)
                rep.add(WARN, "commands", "'%s' looks like a program ChromeOS's foomatic_shell "
                        "won't run (allowed: %s)" % (word, ", ".join(sorted(allowed))))


def emulator_ready(rep):
    if os.access(FOOMATIC_RIP, os.X_OK):
        return True
    rep.add(SKIP, "foomatic verify", "emulator not built: run  bash checker/emulator/build.sh")
    return False


def foomatic_errors(err):
    return re.findall(r".*(?:disallowed|not allowed|Error occurred|Incorrect parameters|"
                      r"too large|Unrecognized|syntax error).*", err)


def check_verify(rep, ppd_path, workdir):
    env = dict(os.environ, FOOMATIC_VERIFY_MODE="true", PPD=os.path.abspath(ppd_path),
               PATH="/bin:/usr/bin:" + os.path.dirname(FOOMATIC_RIP), TMPDIR=workdir)
    pdf = DATA["add_printer_check"]["foomatic_verify_pdf"].encode()
    r = subprocess.run([FOOMATIC_RIP, "1", "chronos", "Untitled", "1", ""], input=pdf,
                       env=env, capture_output=True)
    err = r.stderr.decode(errors="replace")
    bad = foomatic_errors(err)
    if r.returncode == 0 and not bad:
        rep.add(PASS, "foomatic verify", "foomatic_shell accepts every command (ChromeOS's add-printer test)")
    else:
        rep.add(FAIL, "foomatic verify", (bad[0].strip() if bad else
                "foomatic-rip exit %d" % r.returncode)[:300])


def ppd_default_size(text):
    m = re.search(r"^\*DefaultPageSize:\s*(\S+)", text, re.M)
    key = m.group(1) if m else "Letter"
    d = re.search(r'^\*PaperDimension %s(?:/[^:]*)?:\s*"([\d.]+)\s+([\d.]+)"' % re.escape(key),
                  text, re.M)
    return key, (float(d.group(1)), float(d.group(2))) if d else (612.0, 792.0)


def make_test_pdf(w, h, path, pages):
    s = min(w, h)
    ps = "%%!PS\n<< /PageSize [%s %s] >> setpagedevice\n" % (w, h)
    for n in range(1, pages + 1):
        ps += f"""0 setgray {max(2, s/50):.2f} setlinewidth
{s/30:.2f} {s/30:.2f} {w - s/15:.2f} {h - s/15:.2f} rectstroke
/Helvetica-Bold findfont {s/9:.2f} scalefont setfont
{s/12:.2f} {h - s/5:.2f} moveto (PAGE {n}) show
{s/12:.2f} {s/12:.2f} {s/4:.2f} {s/4:.2f} rectfill
0.5 setgray {s/12 + s/3:.2f} {s/12:.2f} {s/4:.2f} {s/4:.2f} rectfill
0 setgray {w*0.7:.2f} {s/12:.2f} moveto {w - s/12:.2f} {s/12 + s/4:.2f} lineto stroke
showpage
"""
    src = path + ".ps"
    open(src, "w").write(ps)
    subprocess.run(["gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
                    "-sOutputFile=" + path, src], check=True)
    os.unlink(src)


def black_bit_hint(text):
    """Polarity from the repository profile the PPD was generated from, if any."""
    m = re.search(r"profiles/([\w.-]+)\.json", text)
    if m:
        for p in glob.glob(os.path.join(ROOT, "families", "*", "profiles", m.group(1) + ".json")):
            return int(json.load(open(p)).get("black_bit", 1))
    return None


def check_print(rep, ppd_path, text, filters, args, outdir, workdir):
    srcs = [s for s, _ in filters_of(text) if "foomatic-rip" in _]
    if not srcs:
        rep.add(SKIP, "print run", "not a foomatic PPD; the emulator only runs foomatic-rip "
                "(ChromeOS's built-in filters need a Chromebook test)")
        return
    name = os.path.splitext(os.path.basename(ppd_path))[0]
    key, (w, h) = ppd_default_size(text)
    if args.pdf:
        pdf, pages_expected = args.pdf, None
    else:
        pdf = os.path.join(workdir, name + "-test.pdf")
        make_test_pdf(w, h, pdf, args.pages)
        pages_expected = args.pages
    env = dict(os.environ, PPD=os.path.abspath(ppd_path), TMPDIR=workdir, PRINTER="emulated")
    if "application/vnd.cups-pdf" in srcs or "application/pdf" in srcs:
        env["CONTENT_TYPE"] = "application/vnd.cups-pdf"
        data_in, mode = open(pdf, "rb").read(), "PDF"
    else:
        if not PDFTOPS:
            rep.add(SKIP, "print run", "PostScript-only PPD and no CUPS pdftops filter here")
            return
        r = subprocess.run([PDFTOPS, "1", "user", "test", "1", ""] + [pdf], env=env,
                           capture_output=True)
        data_in, mode = r.stdout, "PostScript"
    r = subprocess.run([FOOMATIC_RIP, "1", "user", "test", "1", ""], input=data_in,
                       env=env, capture_output=True)
    err = r.stderr.decode(errors="replace")
    job = os.path.join(outdir, name + ".job")
    open(job, "wb").write(r.stdout)
    open(job + ".log", "w").write(err)
    bad = foomatic_errors(err)
    if r.returncode or bad or not r.stdout:
        rep.add(FAIL, "print run", "%s mode, %s: %s" % (mode, key, (bad[0].strip() if bad else
                "foomatic-rip exit %d, %d bytes" % (r.returncode, len(r.stdout)))[:300]))
        return
    msg = "%s mode, %s, %d bytes -> %s" % (mode, key, len(r.stdout), os.path.relpath(job))
    data = r.stdout
    try:
        import preview
    except ImportError:
        preview = None
    bb = black_bit_hint(text)
    pages = None
    if preview and b"\x1dv0" in data:
        pages = preview.escpos_pages(data, 1 if bb is None else bb)
        count, lang = data.count(b"\x1dv0"), "ESC/POS"
    elif preview and re.search(rb"BITMAP \d+,\d+,\d+,\d+,\d+,", data):
        pages = preview.tspl_pages(data, 0 if bb is None else bb)
        count, lang = len(pages), "TSPL"
    if pages is None:
        rep.add(PASS, "print run", msg + " (output format not decoded)")
        return
    if not pages:
        rep.add(FAIL, "print run", msg + "; %s job does not decode (bitmap size mismatch?)" % lang)
        return
    png = os.path.join(outdir, name + ".png")
    pages[0].save(png)
    hist = pages[0].convert("L").histogram()
    black = sum(hist[:128]) / max(1, sum(hist))
    msg += "; %s, %d page(s), preview %s" % (lang, count, os.path.relpath(png))
    if pages_expected and count != pages_expected:
        rep.add(FAIL, "print run", msg + "; expected %d pages" % pages_expected)
    elif black > 0.5:
        rep.add(WARN, "print run", msg + "; %.0f%% black: looks inverted (polarity?)" % (black * 100))
    else:
        rep.add(PASS, "print run", msg)


def check_one(path, args, outdir):
    rep = Report(path)
    try:
        raw = read_ppd(path)
    except OSError as e:
        rep.add(FAIL, "read", str(e))
        return rep
    text = raw.decode("latin-1")
    check_size(rep, raw)
    check_cupstestppd(rep, raw)
    filters = check_filters(rep, text)
    uses_foomatic = 'foomatic-rip"' in text
    if uses_foomatic:
        check_gs_devices(rep, text)
    m = re.search(r'^\*1284DeviceID:\s*"([^"]*)"', text, re.M)
    rep.add(INFO, "device ID", m.group(1) if m else "none (ChromeOS can't auto-match this PPD to a USB printer)")
    if uses_foomatic and emulator_ready(rep):
        with tempfile.TemporaryDirectory() as wd:
            check_verify(rep, path, wd)
            if not args.no_print:
                check_print(rep, path, text, filters, args, outdir, wd)
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ppds", nargs="+")
    ap.add_argument("--pdf", help="print this PDF in the print run (default: generated test page)")
    ap.add_argument("--pages", type=int, default=1, help="pages in the generated test document")
    ap.add_argument("--no-print", action="store_true", help="skip the emulated print run")
    ap.add_argument("--out", default="check-out", help="where jobs and previews go")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    failed = 0
    for path in args.ppds:
        rep = check_one(path, args, args.out)
        rep.show()
        failed += rep.failed
    print("\n%d of %d PPD(s) passed." % (len(args.ppds) - failed, len(args.ppds)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
