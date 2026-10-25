#!/usr/bin/env python3
"""Render a printer job (TSPL or ESC/POS) to a PNG, as the printer would print
it, so you can check a PPD's output without wasting labels or paper.

    python3 families/thermal/preview.py job.bin out.png [--black-bit 0|1]

The language is detected from the data. --black-bit is the printer's bitmap
polarity (TSPL default 0, ESC/POS default 1); use the profile's black_bit.
Needs Pillow (pip install pillow).

TSPL: SIZE, CLS, BITMAP (modes 0/1/2), BAR, REVERSE, PRINT.
ESC/POS: ESC @, GS v 0 rasters stacked top to bottom; feeds and cuts are
shown as a dashed line.
"""
import argparse
import re
import sys

from PIL import Image, ImageDraw

DPI = 203


def tspl_pages(data, black_bit):
    pages, buf, w, h, i = [], None, 0, 0, 0
    while i < len(data):
        j = data.find(b"\n", i)
        line = data[i:j if j >= 0 else len(data)]
        if line.startswith(b"BITMAP "):
            m = re.match(rb"BITMAP (\d+),(\d+),(\d+),(\d+),(\d+),", line)
            x, y, wb, bh, mode = map(int, m.groups())
            start = i + m.end()
            raw = data[start:start + wb * bh]
            for r in range(bh):
                for c in range(wb * 8):
                    if y + r >= h or x + c >= w:
                        continue
                    bit = (raw[r * wb + c // 8] >> (7 - c % 8)) & 1
                    dot = 1 if bit == black_bit else 0
                    if mode == 0:
                        buf[y + r][x + c] = dot
                    elif mode == 1:
                        buf[y + r][x + c] |= dot
                    else:
                        buf[y + r][x + c] ^= dot
            i = start + wb * bh
            continue
        text = line.strip().decode("ascii", "replace")
        if text.startswith("SIZE"):
            def to_dots(v):
                num, *unit = v.split()
                inch = float(num) / 25.4 if unit and unit[0] == "mm" else float(num)
                return int(round(inch * DPI))
            w, h = [to_dots(v) for v in text[5:].split(",")]
        elif text == "CLS":
            buf = [bytearray(w) for _ in range(h)]
        elif text.startswith("BAR ") and buf is not None:
            x, y, bw, bh = map(int, text[4:].split(","))
            for r in range(y, min(h, y + bh)):
                for c in range(x, min(w, x + bw)):
                    buf[r][c] = 1
        elif text.startswith("REVERSE ") and buf is not None:
            x, y, bw, bh = map(int, text[8:].split(","))
            for r in range(y, min(h, y + bh)):
                for c in range(x, min(w, x + bw)):
                    buf[r][c] ^= 1
        elif text.startswith("PRINT") and buf is not None:
            pages.append(to_image(buf, w, h))
        i = (j + 1) if j >= 0 else len(data)
    return pages


def escpos_pages(data, black_bit):
    rows, width, i = [], 0, 0
    while i < len(data):
        if data[i:i + 3] == b"\x1dv0":
            wb = data[i + 4] | data[i + 5] << 8
            h = data[i + 6] | data[i + 7] << 8
            raw = data[i + 8:i + 8 + wb * h]
            width = max(width, wb * 8)
            for r in range(h):
                row = bytearray(wb * 8)
                for c in range(wb * 8):
                    bit = (raw[r * wb + c // 8] >> (7 - c % 8)) & 1
                    row[c] = 1 if bit == black_bit else 0
                rows.append(row)
            i += 8 + wb * h
        elif data[i:i + 2] == b"\x1dV":
            rows.append("CUT")
            i += 3 if data[i + 2] in (0, 1, 48, 49) else 4
        elif data[i:i + 2] == b"\x1bd":
            rows.extend([bytearray(width or 8)] * (data[i + 2] * 24))
            i += 3
        else:
            i += 1
    if not rows:
        return []
    width = width or 8
    img = Image.new("L", (width, sum(1 if r == "CUT" else 1 for r in rows)), 255)
    px = img.load()
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(rows):
        if row == "CUT":
            for x in range(0, width, 12):
                draw.line([(x, y), (x + 6, y)], fill=128)
            continue
        for x in range(min(width, len(row))):
            if row[x]:
                px[x, y] = 0
    return [img]


def to_image(buf, w, h):
    img = Image.new("L", (w, h), 255)
    px = img.load()
    for y in range(h):
        for x in range(w):
            if buf[y][x]:
                px[x, y] = 0
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("png")
    ap.add_argument("--black-bit", type=int, choices=(0, 1))
    args = ap.parse_args()
    data = open(args.job, "rb").read()
    if b"\x1dv0" in data:
        pages = escpos_pages(data, 1 if args.black_bit is None else args.black_bit)
    else:
        pages = tspl_pages(data, 0 if args.black_bit is None else args.black_bit)
    if not pages:
        sys.exit("nothing printable found")
    gap = 16
    out = Image.new("L", (max(p.width for p in pages),
                          sum(p.height for p in pages) + gap * (len(pages) - 1)), 200)
    y = 0
    for p in pages:
        out.paste(p, (0, y))
        y += p.height + gap
    out.save(args.png)
    print("%d page(s) -> %s" % (len(pages), args.png))


if __name__ == "__main__":
    main()
