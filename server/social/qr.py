"""A small QR code encoder (byte mode, versions 1-20, error correction L or M), drawn as SVG.

Used to show an authenticator set-up link (otpauth://...) as a code a phone can scan. It follows ISO/IEC 18004 in the
same way as Project Nayuki's reference generator; tests/test_friends_admin.py checks finished symbols against
reference matrices. The text form of the secret is always shown next to it, so a scan is never the only way.
"""
from __future__ import annotations

# error-correction codewords per block, and number of blocks, for versions 1..20 (index 0 unused)
_ECC_PER_BLOCK = {
    "L": (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28),
    "M": (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26),
}
_BLOCKS = {
    "L": (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8),
    "M": (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16),
}
_FORMAT_ECL = {"L": 1, "M": 0}
MAX_VERSION = 20


class QRError(ValueError):
    pass


def _raw_modules(ver: int) -> int:
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        result -= (25 * n - 10) * n - 55
        if ver >= 7:
            result -= 36
    return result


def _data_codewords(ver: int, ecl: str) -> int:
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ecl][ver] * _BLOCKS[ecl][ver]


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: list, divisor: list) -> list:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _alignment_positions(ver: int) -> list:
    if ver == 1:
        return []
    n = ver // 7 + 2
    size = ver * 4 + 17
    step = (ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    tail = [size - 7 - i * step for i in range(n - 1)]
    return [6] + tail[::-1]


class _Symbol:
    def __init__(self, ver: int, ecl: str) -> None:
        self.ver, self.ecl, self.size = ver, ecl, ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.func = [[False] * self.size for _ in range(self.size)]

    def set(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.func[y][x] = True

    def draw_function_patterns(self) -> None:
        size = self.size
        for i in range(size):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _alignment_positions(self.ver)
        last = len(pos) - 1
        for i, ax in enumerate(pos):
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = size - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def draw_format(self, mask: int) -> None:
        data = _FORMAT_ECL[self.ecl] << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1
        size = self.size
        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, size - 15 + i, bit(i))
        self.set(8, size - 8, True)

    def draw_codewords(self, data: list) -> None:
        size, i = self.size, 0
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = size - 1 - vert if upward else vert
                    if not self.func[y][x] and i < len(data) * 8:
                        self.dark[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        test = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
                lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
                lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
                lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.func[y][x] and test(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        """The four penalty rules of the standard (runs, 2x2 blocks, finder-like patterns, dark/light balance)."""
        size, rows = self.size, self.dark
        cols = [[rows[y][x] for y in range(size)] for x in range(size)]
        score = 0

        def add(history: list, run: int) -> None:
            if history[0] == 0:
                run += size                                 # the light border before the first run
            history.insert(0, run)
            del history[7:]

        def patterns(h: list) -> int:
            n = h[1]
            core = n > 0 and h[2] == h[4] == h[5] == n and h[3] == n * 3
            return int(core and h[0] >= n * 4 and h[6] >= n) + int(core and h[6] >= n * 4 and h[0] >= n)

        for line in rows + cols:
            color, run, history = False, 0, [0] * 7
            for v in line:
                if v == color:
                    run += 1
                    if run == 5:
                        score += 3
                    elif run > 5:
                        score += 1
                else:
                    add(history, run)
                    if not color:
                        score += patterns(history) * 40
                    color, run = v, 1
            if color:                                       # end the last dark run, then the light border after it
                add(history, run)
                run = 0
            add(history, run + size)
            score += patterns(history) * 40
        for y in range(size - 1):
            for x in range(size - 1):
                v = rows[y][x]
                if v == rows[y][x + 1] == rows[y + 1][x] == rows[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(r) for r in rows)
        total = size * size
        k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        return score + max(0, k) * 10


def _encode_data(data: bytes, ver: int, ecl: str) -> list | None:
    count_bits = 8 if ver <= 9 else 16
    capacity = _data_codewords(ver, ecl) * 8
    bits = [0, 1, 0, 0]
    bits += [(len(data) >> i) & 1 for i in range(count_bits - 1, -1, -1)]
    for b in data:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    if len(bits) > capacity:
        return None
    bits += [0] * min(4, capacity - len(bits))
    bits += [0] * (-len(bits) % 8)
    pad = 0xEC
    while len(bits) < capacity:
        bits += [(pad >> i) & 1 for i in range(7, -1, -1)]
        pad ^= 0xEC ^ 0x11
    return [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]


def _interleave(data: list, ver: int, ecl: str) -> list:
    nblocks, ecc_len = _BLOCKS[ecl][ver], _ECC_PER_BLOCK[ecl][ver]
    raw = _raw_modules(ver) // 8
    nshort = nblocks - raw % nblocks
    short_len = raw // nblocks
    divisor = _rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(nblocks):
        dat = data[k:k + short_len - ecc_len + (0 if i < nshort else 1)]
        k += len(dat)
        ecc = _rs_remainder(dat, divisor)
        if i < nshort:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len - ecc_len or j >= nshort:
                out.append(blk[i])
    return out


def encode(text, ecl: str = "M", mask: int | None = None, version: int | None = None) -> list:
    """The finished symbol as rows of booleans (True = dark), without the quiet zone."""
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    if ecl not in _BLOCKS:
        raise QRError("error correction level must be L or M")
    for ver in ([version] if version else range(1, MAX_VERSION + 1)):
        codewords = _encode_data(data, ver, ecl)
        if codewords is not None:
            break
    else:
        raise QRError("too much text for a QR code here")
    sym = _Symbol(ver, ecl)
    sym.draw_function_patterns()
    sym.draw_codewords(_interleave(codewords, ver, ecl))
    if mask is None:
        best = None
        for m in range(8):
            sym.apply_mask(m)
            sym.draw_format(m)
            score = sym.penalty()
            if best is None or score < best[0]:
                best = (score, m)
            sym.apply_mask(m)                               # masking twice undoes it
        mask = best[1]
    sym.apply_mask(mask)
    sym.draw_format(mask)
    return sym.dark


def svg(text, scale: int = 6, ecl: str = "M", dark: str = "#000", light: str = "#fff") -> str:
    """An SVG image with the standard four-module quiet zone; one path, crisp edges."""
    rows = encode(text, ecl)
    n = len(rows) + 8
    parts = [f"M{x + 4},{y + 4}h1v1h-1z" for y, row in enumerate(rows) for x, v in enumerate(row) if v]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n * scale}" height="{n * scale}" '
            f'shape-rendering="crispEdges" role="img" aria-label="QR code"><rect width="{n}" height="{n}" fill="{light}"/>'
            f'<path fill="{dark}" d="{"".join(parts)}"/></svg>')
