#!/usr/bin/env python3
"""Probe a thermal printer and write a draft printer profile.

Sends a short series of numbered test prints straight to the printer (no
driver, no CUPS) and asks you what came out. From your answers it writes a
draft profile for families/thermal/ppdgen.py.

Every test print shows its number twice: as N small squares in the top-left
corner and as large digits in the top-right corner.

Examples
  sudo python3 families/thermal/probe.py                         # auto-detect USB printer
  sudo python3 families/thermal/probe.py --size 3x2              # TSPL labels, 3 x 2 inch
  python3 families/thermal/probe.py --device socket://192.168.1.50:9100 --language escpos
  sudo python3 families/thermal/probe.py --device /dev/ttyUSB0 --baud 19200 --language escpos
  sudo python3 families/thermal/probe.py --list                  # show detected printers only

Supported languages: tspl, escpos. Others (ZPL, EPL, CPCL) are welcome as
contributions; see families/thermal/adding-a-printer.md.
"""
import argparse
import glob
import json
import os
import re
import select
import socket
import sys
import termios
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bitmap import test_card  # noqa: E402

DPI_DEFAULT = 203


# ----------------------------------------------------------------------------
# Transports
# ----------------------------------------------------------------------------

class Transport:
    def write(self, data):
        raise NotImplementedError

    def read(self, timeout=1.5):
        return b""

    def close(self):
        pass


class FileTransport(Transport):
    """Kernel USB printer device (/dev/usb/lpN) or a serial port."""

    def __init__(self, path, baud=None):
        # O_APPEND is ignored by device files; it lets a plain file stand in
        # for a printer when testing the tool itself.
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_APPEND)
        if baud:
            attrs = termios.tcgetattr(self.fd)
            speed = getattr(termios, "B%d" % baud)
            attrs[0] = 0                     # iflag: raw
            attrs[1] = 0                     # oflag: raw
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0                     # lflag: raw
            attrs[4] = attrs[5] = speed
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def write(self, data):
        sent = 0
        while sent < len(data):
            sent += os.write(self.fd, data[sent:sent + 4096])

    def read(self, timeout=1.5):
        got = b""
        end = time.time() + timeout
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if not r:
                continue
            try:
                chunk = os.read(self.fd, 256)
            except OSError:
                break
            if chunk:
                got += chunk
        return got

    def close(self):
        os.close(self.fd)


class SocketTransport(Transport):
    """Raw TCP, usually port 9100 (AppSocket / JetDirect)."""

    def __init__(self, host, port):
        self.s = socket.create_connection((host, port), timeout=10)

    def write(self, data):
        self.s.sendall(data)

    def read(self, timeout=1.5):
        self.s.settimeout(timeout)
        try:
            return self.s.recv(256)
        except (socket.timeout, OSError):
            return b""

    def close(self):
        self.s.close()


def open_transport(device, baud):
    if device.startswith("socket://"):
        m = re.match(r"socket://([^:/]+)(?::(\d+))?", device)
        return SocketTransport(m.group(1), int(m.group(2) or 9100))
    return FileTransport(device, baud)


# ----------------------------------------------------------------------------
# Detection
# ----------------------------------------------------------------------------

def parse_1284(device_id):
    fields = {}
    for part in device_id.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            fields[k.strip().upper()] = v.strip()
    return fields


def language_from_cmd(cmd):
    c = cmd.upper().replace(" ", "")
    if "TSPL" in c or "TSC" in c:
        return "tspl"
    # Many receipt printers just say "EPSON" (meaning Epson's ESC/POS), e.g.
    # Rongta: COMMENDSET:EPSON. "ESC/P", "ESCP2", "ESCPL2" are Epson inkjet
    # languages and are not matched here.
    if "ESC/POS" in c or "ESCPOS" in c or c.startswith("POS") or c == "EPSON":
        return "escpos"
    if "ZPL" in c:
        return "zpl"
    if "EPL" in c:
        return "epl"
    if "CPCL" in c:
        return "cpcl"
    return None


def detect_usb():
    """Return a list of dicts for /dev/usb/lp* printers."""
    found = []
    for lp in sorted(glob.glob("/sys/class/usbmisc/lp*")):
        name = os.path.basename(lp)
        info = {"device": "/dev/usb/" + name}
        try:
            info["ieee1284_id"] = open(os.path.join(lp, "device/ieee1284_id")).read().strip()
        except OSError:
            info["ieee1284_id"] = ""
        usbdev = os.path.realpath(os.path.join(lp, "device/.."))
        for key, fname in (("vid", "idVendor"), ("pid", "idProduct"),
                           ("manufacturer", "manufacturer"), ("product", "product")):
            try:
                info[key] = open(os.path.join(usbdev, fname)).read().strip()
            except OSError:
                pass
        f = parse_1284(info["ieee1284_id"])
        # Key names vary: CMD, COMMAND SET, COMMANDSET, even COMMENDSET (Rongta).
        cmd = next((f[k] for k in ("CMD", "COMMAND SET", "COMMANDSET", "COMMENDSET")
                    if k in f), "")
        info["language"] = language_from_cmd(cmd)
        mfg = f.get("MFG", f.get("MANUFACTURER", info.get("manufacturer", "")))
        # Some printers report a placeholder maker ("USB") and the real one
        # in DESCRIPTION (Rongta: DESCRIPTION:RONGTA).
        if mfg.upper() in ("", "USB", "PRINTER", "GENERIC") and f.get("DESCRIPTION"):
            mfg = f["DESCRIPTION"].title()
        info["mfg"] = mfg
        info["mdl"] = f.get("MDL", f.get("MODEL", info.get("product", "")))
        found.append(info)
    return found


# ----------------------------------------------------------------------------
# Test suites
# ----------------------------------------------------------------------------

def crlf(*lines):
    return "".join(l + "\r\n" for l in lines).encode()


def tspl_suite(args):
    w_in, h_in = (float(v) for v in args.size.lower().split("x"))
    W = int(round(w_in * args.dpi))
    H = int(round(h_in * args.dpi))
    wb = (W + 7) // 8
    size = "SIZE %.2f mm,%.2f mm" % (w_in * 25.4, h_in * 25.4)
    head = crlf(size, "GAP %.2f mm,0.00 mm" % args.gap_mm, "REFERENCE 0,0", "OFFSET 0",
                "DENSITY 8", "SPEED 4", "DIRECTION 0,0", "CLS")

    def job(n, mode, black_bit, extra=b""):
        bm, sq = test_card(W, H, n)
        return (head + b"BITMAP 0,0,%d,%d,%d," % (wb, H, mode) + bm.encode(black_bit)
                + b"\r\n" + extra + b"PRINT 1,1\r\n"), sq

    tests = []
    data, _ = job(1, 1, 0)
    tests.append(dict(key="mode1_black0", title="BITMAP mode 1, 0 = black",
                      expect="black on white if the printer uses 0 = black, otherwise a negative",
                      data=data))
    data, _ = job(2, 1, 1)
    tests.append(dict(key="mode1_black1", title="BITMAP mode 1, 1 = black",
                      expect="black on white if the printer uses 1 = black (one of tests 1/2 is a negative)",
                      data=data))
    data, _ = job(3, 0, 0)
    tests.append(dict(key="mode0_black0", title="BITMAP mode 0, 0 = black",
                      expect="anything printed? (some firmware drops the whole job)", data=data))
    bm, sq = test_card(W, H, 4)
    x0, y0, x1, y1 = sq
    data, _ = job(4, 1, 0, crlf("REVERSE %d,%d,%d,%d" % (x0, y0, x1 - x0, y1 - y0)))
    tests.append(dict(key="reverse", title="REVERSE command",
                      expect="the big square is WHITE if REVERSE is supported", data=data))
    data, _ = job(5, 1, 0, crlf('TEXT %d,%d,"3",0,1,1,"OK"' % (x1 + 20, y0)))
    tests.append(dict(key="text", title="TEXT command (built-in font)",
                      expect="'OK' printed next to the big square if TEXT is supported",
                      data=data))
    return tests, dict(width_dots=W, height_dots=H, size_in=(w_in, h_in))


def escpos_suite(args):
    W = args.dots
    wb = (W + 7) // 8
    init = b"\x1b@"
    feed_cut = b"\x1bd\x04" + b"\x1dVB\x00"          # feed 4 lines, partial cut

    def raster(n, rows, black_bit):
        bm, _ = test_card(W, rows, n)
        return (b"\x1dv0\x00" + bytes([wb & 0xFF, wb >> 8, rows & 0xFF, rows >> 8])
                + bm.encode(black_bit))

    tests = []
    tests.append(dict(key="text", title="plain text + feed + partial cut (GS V 66)",
                      expect="text 'PROBE TEST 1: ESC/POS TEXT', then the paper is cut",
                      data=init + b"PROBE TEST 1: ESC/POS TEXT\n" + b"Line 2\n" + feed_cut))
    card = args.card_rows
    tests.append(dict(key="raster_black1", title="GS v 0 raster, 1 = black",
                      expect="black on white if the printer uses 1 = black, otherwise a negative",
                      data=init + raster(2, card, 1) + feed_cut))
    tests.append(dict(key="raster_black0", title="GS v 0 raster, 0 = black",
                      expect="usually a NEGATIVE (white on black); black on white only if the printer uses 0 = black",
                      data=init + raster(3, card, 0) + feed_cut))
    tall = args.tall_rows
    tests.append(dict(key="raster_tall", title="one tall GS v 0 raster (%d rows, %.0f mm)"
                      % (tall, tall / args.dpi * 25.4),
                      expect="one long card with border on all four sides, nothing cut off",
                      data=init + raster(4, tall, 1) + feed_cut))
    cuts = [(b"A", b"\x1dV\x00", "GS V 0 (full cut)"),
            (b"B", b"\x1dV\x01", "GS V 1 (partial cut)"),
            (b"C", b"\x1dVA\x03", "GS V 65 3 (feed + full cut)"),
            (b"D", b"\x1dVB\x03", "GS V 66 3 (feed + partial cut)")]
    data = init + b"PROBE TEST 5: CUT COMMANDS\n"
    for letter, cmd, name in cuts:
        data += b"\n" + letter + b": " + name.encode() + b"\n\n\n\n" + cmd
    tests.append(dict(key="cuts", title="cut commands A-D",
                      expect="note which letters were cut after (e.g. 'A B D'); "
                             "C/D also feed first",
                      data=data))
    if args.drawer:
        tests.append(dict(key="drawer", title="cash drawer kick (ESC p 0 25 250)",
                          expect="the cash drawer opens",
                          data=init + b"\x1bp\x00\x19\xfa"))
    return tests, dict(width_dots=W)


def tspl_status(t):
    return [("ESC !? status byte", t.write(b"\x1b!?") or t.read()),
            ("~!T model name", t.write(b"~!T\r\n") or t.read())]


def escpos_status(t):
    out = []
    for n in (1, 2, 3, 4):
        t.write(b"\x10\x04" + bytes([n]))
        out.append(("DLE EOT %d real-time status" % n, t.read(1.0)))
    for n, what in ((66, "maker"), (67, "model name"), (65, "firmware")):
        t.write(b"\x1dI" + bytes([n]))
        out.append(("GS I %d %s" % (n, what), t.read(1.0)))
    return out


SUITES = {"tspl": (tspl_suite, tspl_status), "escpos": (escpos_suite, escpos_status)}


# ----------------------------------------------------------------------------
# Profile drafting
# ----------------------------------------------------------------------------

def yes(ans):
    """Printed the right way round: 'y', 'b', 'black on white', 'normal'."""
    a = ans.strip().lower()
    return (a.startswith("y") or a.startswith("normal") or a == "b"
            or a.startswith("black on"))


def negative(ans):
    """Printed as a negative: 'n'... is ambiguous with 'no', so only accept
    words: 'neg', 'negative', 'inverted', 'white on black'."""
    a = ans.strip().lower()
    return a.startswith("neg") or "invert" in a or "white on black" in a


def draft_profile(args, info, lang, answers, geometry, status):
    mfg = (info.get("mfg") or "Unknown").strip()
    mdl = (info.get("mdl") or "Printer").strip()
    pid = re.sub(r"[^a-z0-9]+", "-", ("%s-%s" % (mfg, mdl)).lower()).strip("-")
    prof = {
        "id": pid,
        "manufacturer": mfg,
        "model": mdl,
        "status": "draft",
        "ieee1284_id": info.get("ieee1284_id", ""),
        "usb": {"vid": info.get("vid", ""), "pid": info.get("pid", "")},
        "language": lang,
        "dpi": args.dpi,
        "probe": {"answers": answers,
                  "status_replies": {k: v.hex() for k, v in status}},
    }
    if lang == "tspl":
        b0 = answers.get("mode1_black0", "")
        b1 = answers.get("mode1_black1", "")
        if negative(b0) or (yes(b1) and not yes(b0)):
            prof["black_bit"] = 1
        else:
            prof["black_bit"] = 0
        mode = 1 if (yes(b0) or yes(b1) or negative(b0) or negative(b1)) else 0
        w_in, h_in = geometry["size_in"]
        prof["tspl"] = {
            "bitmap_mode": mode,
            "prefix": ["REFERENCE 0,0", "OFFSET 0"],
            "after_options": ["DIRECTION 0,0"],
            "reverse_supported": yes(answers.get("reverse", "")),
            "text_supported": yes(answers.get("text", "")),
        }
        prof["sizes"] = [{"width_mm": round(w_in * 25.4, 2),
                          "height_mm": round(h_in * 25.4, 2), "default": True}]
    elif lang == "escpos":
        g1 = answers.get("raster_black1", "")
        g0 = answers.get("raster_black0", "")
        prof["black_bit"] = 0 if ((yes(g0) and not yes(g1)) or negative(g1)) else 1
        cuts = answers.get("cuts", "").upper()
        cut_hex = None
        for letter, hx in (("D", "1d564203"), ("B", "1d5601"), ("C", "1d564103"),
                           ("A", "1d5600")):
            if letter in cuts:
                cut_hex = hx
                break
        width_mm = round(geometry["width_dots"] / args.dpi * 25.4, 1)
        max_rows = args.tall_rows if yes(answers.get("raster_tall", "")) else args.card_rows
        lengths = [L for L in (50, 100, 150, 200, 297, 400)
                   if round(L / 25.4 * args.dpi) <= max_rows] or [40]
        default_len = 200 if 200 in lengths else lengths[-1]
        prof["sizes"] = [{"key": "X%dMMY%d" % (round(width_mm), L),
                          "label": "%g mm print width, %d mm long" % (width_mm, L),
                          "width_mm": width_mm, "height_mm": L,
                          **({"default": True} if L == default_len else {})}
                         for L in lengths]
        prof["escpos"] = {
            "printable_width_mm": width_mm,
            "max_rows": max_rows,
            "init_hex": "1b40",
            "feed_lines_default": 4,
            "cut_hex": {"partial": cut_hex or "1d564200", "full": "1d564100"},
            "drawer_hex": "1b700019fa" if yes(answers.get("drawer", "")) else "",
        }
    return prof


# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", help="/dev/usb/lp0, socket://host:9100 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, help="serial speed, e.g. 9600 or 19200")
    ap.add_argument("--language", choices=sorted(SUITES), help="override detection")
    ap.add_argument("--dpi", type=int, default=DPI_DEFAULT)
    ap.add_argument("--size", default="3x2", help="TSPL label size in inches, WxH (default 3x2)")
    ap.add_argument("--gap-mm", type=float, default=3.0, help="TSPL label gap (default 3)")
    ap.add_argument("--dots", type=int, default=576,
                    help="ESC/POS printable width in dots (576 = 80 mm paper, 384 = 58 mm)")
    ap.add_argument("--card-rows", type=int, default=320, help="ESC/POS test card height")
    ap.add_argument("--tall-rows", type=int, default=1600, help="ESC/POS tall raster test height")
    ap.add_argument("--drawer", action="store_true", help="also test the cash drawer kick")
    ap.add_argument("--only", type=int, help="run just this test number")
    ap.add_argument("--out", help="where to write the draft profile (JSON)")
    ap.add_argument("--list", action="store_true", help="list detected USB printers and exit")
    args = ap.parse_args()

    usb = detect_usb()
    if args.list:
        for p in usb:
            print(json.dumps(p, indent=2))
        if not usb:
            print("No /dev/usb/lp* printers found.")
        return

    info = {}
    if args.device:
        if args.device.startswith("/dev/usb/"):
            info = next((p for p in usb if p["device"] == args.device), {})
    elif usb:
        info = usb[0]
        args.device = info["device"]
        print("Using %s: %s %s  (%s)" % (info["device"], info.get("mfg"), info.get("mdl"),
                                          info.get("ieee1284_id")))
    else:
        sys.exit("No USB printer found. Use --device (see --help).")

    lang = args.language or info.get("language")
    if lang not in SUITES:
        sys.exit("Unknown or unsupported printer language %r. Use --language tspl|escpos.\n"
                 "Detected device ID: %s" % (lang, info.get("ieee1284_id", "")))

    suite, status_fn = SUITES[lang]
    tests, geometry = suite(args)
    report_path = args.out or "probe-%s.json" % (re.sub(r"[^A-Za-z0-9]+", "-",
                                                        info.get("mdl", "printer")).strip("-"))
    print("\nLanguage: %s.  %d tests.  Answers go to %s\n" % (lang, len(tests), report_path))

    t = open_transport(args.device, args.baud)
    status = []
    try:
        status = status_fn(t)
    except OSError as e:
        print("(status queries failed: %s)" % e)
    for name, reply in status:
        print("  %-28s -> %s" % (name, reply.hex() if reply else "(no reply)"))
    t.close()

    answers = {}
    for n, test in enumerate(tests, 1):
        if args.only and n != args.only:
            continue
        print("\n== TEST %d: %s ==" % (n, test["title"]))
        print("   looks right if: %s" % test["expect"])
        t = open_transport(args.device, args.baud)
        try:
            t.write(test["data"])
        except OSError as e:
            print("   write failed: %s  (power-cycle the printer, then rerun with --only %d)"
                  % (e, n + 1))
            answers[test["key"]] = "write failed: %s" % e
            break
        finally:
            t.close()
        time.sleep(3)
        answers[test["key"]] = input("   TEST %d: [b]lack on white / [n]egative (white on black) / "
                                     "nothing / describe: " % n)

    prof = draft_profile(args, info, lang, answers, geometry, status)
    with open(report_path, "w") as f:
        json.dump(prof, f, indent=2)
        f.write("\n")
    print("\nDraft profile written to %s" % report_path)
    print("Next: review it, copy it to families/thermal/profiles/, and run  python3 families/thermal/ppdgen.py %s"
          % report_path)


if __name__ == "__main__":
    main()
