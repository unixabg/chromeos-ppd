#!/usr/bin/env python3
"""Run PPDs through an emulation of ChromeOS's print pipeline.

    bash tests/chromeos/build.sh                 # once
    python3 tests/chromeos/emulate.py            # every ppd/*.ppd
    python3 tests/chromeos/emulate.py ppd/x.ppd --pdf my-label.pdf

For each PPD it prints a test page at the PPD's default size (or your PDF):

  PDF-mode PPDs (printer wants 1 = black):
      PDF -> foomatic-rip (ChromeOS-patched, ChromeOS foomatic_shell)
  PostScript-mode PPDs (printer wants 0 = black):
      PDF -> pdftops + pstops with the PPD (inserts the PPD's PostScript
             options, as CUPS does) -> foomatic-rip (as above)

It fails if foomatic_shell rejects anything, if the job is empty, or if
the preview shows a mostly black page (wrong polarity). Output jobs and
preview PNGs go to tests/out/.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(HERE, "build")
FOOMATIC_RIP = os.path.join(BUILD, "cups-filters", "foomatic-rip")
PDFTOPS = next((p for p in ("/usr/lib/cups/filter/pdftops",
                            "/usr/libexec/cups/filter/pdftops") if os.path.exists(p)), None)
OUT = os.path.join(ROOT, "tests", "out")

sys.path.insert(0, os.path.join(ROOT, "tools"))
import preview  # noqa: E402


def ppd_info(path):
    text = open(path, encoding="latin-1").read()
    default = re.search(r"^\*DefaultPageSize:\s*(\S+)", text, re.M).group(1)
    dims = re.search(r'^\*PaperDimension %s/[^:]*:\s*"([\d.]+) ([\d.]+)"' % re.escape(default),
                     text, re.M)
    pdf_mode = "application/vnd.cups-pdf 0 foomatic-rip" in text
    return dict(default=default, w=float(dims.group(1)), h=float(dims.group(2)),
                pdf_mode=pdf_mode)


def make_test_pdf(w, h, path):
    """A test page: border, title, solid and grey squares, a diagonal."""
    s = min(w, h)
    ps = f"""%!PS
<< /PageSize [{w} {h}] >> setpagedevice
0 setgray {max(2, s/50):.2f} setlinewidth
{s/30:.2f} {s/30:.2f} {w - s/15:.2f} {h - s/15:.2f} rectstroke
/Helvetica-Bold findfont {s/9:.2f} scalefont setfont
{s/12:.2f} {h - s/5:.2f} moveto (TEST PAGE) show
{s/12:.2f} {s/12:.2f} {s/4:.2f} {s/4:.2f} rectfill
0.5 setgray {s/12 + s/3:.2f} {s/12:.2f} {s/4:.2f} {s/4:.2f} rectfill
0 setgray {w*0.7:.2f} {s/12:.2f} moveto {w - s/12:.2f} {s/12 + s/4:.2f} lineto stroke
showpage
"""
    with tempfile.NamedTemporaryFile("w", suffix=".ps", delete=False) as f:
        f.write(ps)
    subprocess.run(["gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
                    "-sOutputFile=" + path, f.name], check=True)
    os.unlink(f.name)


def run(ppd, pdf, job_out):
    info = ppd_info(ppd)
    env = dict(os.environ, PPD=os.path.abspath(ppd),
               TMPDIR=tempfile.gettempdir(), PRINTER="emulated")
    log = []
    if info["pdf_mode"]:
        env["CONTENT_TYPE"] = "application/vnd.cups-pdf"
        data_in = open(pdf, "rb").read()
    else:
        if not PDFTOPS:
            return False, "no CUPS pdftops filter found (install cups-filters)", info
        r = subprocess.run([PDFTOPS, "1", "user", "test", "1", "", pdf], env=env,
                           capture_output=True)
        log.append(r.stderr.decode(errors="replace"))
        if r.returncode:
            return False, "pdftops failed", info
        data_in = r.stdout
        if b"settransfer" not in data_in:
            return False, "pstops did not insert the Polarity option", info
        env["CONTENT_TYPE"] = "application/vnd.cups-postscript"
    r = subprocess.run([FOOMATIC_RIP, "1", "user", "test", "1", ""], input=data_in,
                       env=env, capture_output=True)
    err = r.stderr.decode(errors="replace")
    open(job_out + ".log", "w").write("\n".join(log) + err)
    open(job_out, "wb").write(r.stdout)
    bad = re.findall(r".*(?:disallowed|not allowed|Error occurred).*", err)
    if r.returncode or bad or not r.stdout:
        return False, (bad[0] if bad else "foomatic-rip exit %d, %d bytes"
                       % (r.returncode, len(r.stdout))), info
    return True, "%d bytes" % len(r.stdout), info


def black_fraction(img):
    hist = img.convert("L").histogram()
    return sum(hist[:128]) / max(1, sum(hist))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ppds", nargs="*")
    ap.add_argument("--pdf", help="print this PDF instead of a generated test page")
    args = ap.parse_args()
    if not os.access(FOOMATIC_RIP, os.X_OK):
        sys.exit("Run  bash tests/chromeos/build.sh  first.")
    os.makedirs(OUT, exist_ok=True)
    ppds = args.ppds or sorted(glob.glob(os.path.join(ROOT, "ppd", "*.ppd")))
    failed = 0
    for ppd in ppds:
        name = os.path.splitext(os.path.basename(ppd))[0]
        info = ppd_info(ppd)
        pdf = args.pdf or os.path.join(OUT, name + "-test.pdf")
        if not args.pdf:
            make_test_pdf(info["w"], info["h"], pdf)
        job = os.path.join(OUT, name + ".job")
        ok, msg, info = run(ppd, pdf, job)
        if ok:
            pages = (preview.escpos_pages(open(job, "rb").read(), 1) if info["pdf_mode"]
                     else preview.tspl_pages(open(job, "rb").read(), 0))
            if not pages:
                ok, msg = False, "job has no printable image"
            else:
                pages[0].save(os.path.join(OUT, name + ".png"))
                bf = black_fraction(pages[0])
                msg += ", %.0f%% black" % (bf * 100)
                if bf > 0.5:
                    ok, msg = False, msg + " (looks inverted)"
        print("%-6s %-28s %s mode, %s: %s" % ("PASS" if ok else "FAIL", name,
                                              "PDF" if info["pdf_mode"] else "PostScript",
                                              info["default"], msg))
        failed += not ok
    print("\nJobs, logs and previews: %s" % os.path.relpath(OUT, os.getcwd()))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
