"""Tiny 1-bit bitmap helper used by the probe tool (no third-party modules).

Pixels are stored as 1 = black. encode() packs rows MSB-first into bytes and
can emit either polarity, because printers disagree (TSPL usually 0 = black,
ESC/POS 1 = black).
"""

# 7-segment layout:  a=top b=upper-right c=lower-right d=bottom
#                    e=lower-left f=upper-left g=middle
_SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


class Bitmap:
    def __init__(self, width, height):
        self.width_bytes = (width + 7) // 8
        self.width = self.width_bytes * 8
        self.height = height
        self.px = [bytearray(self.width) for _ in range(height)]

    def rect(self, x0, y0, x1, y1):
        """Fill [x0, x1) x [y0, y1), clipped to the bitmap."""
        x0, x1 = max(0, x0), min(self.width, x1)
        for y in range(max(0, y0), min(self.height, y1)):
            row = self.px[y]
            for x in range(x0, x1):
                row[x] = 1

    def frame(self, t):
        w, h = self.width, self.height
        self.rect(0, 0, w, t)
        self.rect(0, h - t, w, h)
        self.rect(0, 0, t, h)
        self.rect(w - t, 0, w, h)

    def line(self, x0, y0, x1, y1, t):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(steps + 1):
            x = x0 + (x1 - x0) * i // steps
            y = y0 + (y1 - y0) * i // steps
            self.rect(x - t // 2, y - t // 2, x + t // 2 + 1, y + t // 2 + 1)

    def digit(self, ch, x, y, h):
        """Draw one 7-segment digit of height h with its top-left at (x, y)."""
        w = h // 2
        t = max(3, h // 8)
        segs = _SEGMENTS.get(ch, "")
        m = y + h // 2
        if "a" in segs: self.rect(x, y, x + w, y + t)
        if "d" in segs: self.rect(x, y + h - t, x + w, y + h)
        if "g" in segs: self.rect(x, m - t // 2, x + w, m + t - t // 2)
        if "f" in segs: self.rect(x, y, x + t, m)
        if "e" in segs: self.rect(x, m, x + t, y + h)
        if "b" in segs: self.rect(x + w - t, y, x + w, m)
        if "c" in segs: self.rect(x + w - t, m, x + w, y + h)
        return x + w + max(4, h // 6)

    def number(self, text, x, y, h):
        for ch in str(text):
            x = self.digit(ch, x, y, h)
        return x

    def encode(self, black_bit):
        """Pack to bytes. black_bit is 1 if the printer wants 1 = black."""
        out = bytearray()
        flip = 0x00 if black_bit == 1 else 0xFF
        for row in self.px:
            for b in range(self.width_bytes):
                v = 0
                base = b * 8
                for bit in range(8):
                    v = (v << 1) | row[base + bit]
                out.append(v ^ flip)
        return bytes(out)


def test_card(width, height, number):
    """The standard probe image: border, `number` small squares top-left,
    the number in large digits, a solid square and a diagonal line.
    Returns (bitmap, big_square_rect)."""
    bm = Bitmap(width, height)
    W, H = bm.width, bm.height
    bm.frame(max(4, min(W, H) // 60))
    pad = max(10, min(W, H) // 25)
    s = max(10, min(W // 14, H // 9))
    for i in range(number):
        x = pad + i * (s + s // 2)
        bm.rect(x, pad, x + s, pad + s)
    top = pad + s + pad
    digit_h = max(24, min(H // 3, W // 6))
    bm.number(number, W - pad - (digit_h // 2 + digit_h // 6) * len(str(number)), pad, digit_h)
    big = max(16, min(W // 3, H - top - pad))
    sq = (pad, top, pad + big, top + big)
    bm.rect(*sq)
    bm.line(pad + big + pad, top, W - pad, min(H - pad, top + big), max(3, big // 20))
    return bm, sq
