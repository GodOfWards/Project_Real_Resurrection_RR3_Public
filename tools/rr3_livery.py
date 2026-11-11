#!/usr/bin/env python3
"""Turn RR3 car livery textures into PNGs and back.

Livery textures are vehicles/<car>/livery/<car>_ext*.etc.dds.z in the game
data (files/.depot/ under Android/data/com.ea.games.r3_row/). A .z file is a
4-byte little-endian uncompressed size followed by a zlib stream. Inside is a
DDS file with FourCC "ETC " (ETC1, no alpha), usually 1024x1024 with a full
mip chain.

The game's DDS loader accepts only DXT1/3/5, ATC, ATCI, ATCA, "ETC " and plain
RGB/RGBA (no ETC2, no DX10 header), so `import` writes ETC1 with the same
header as the original file.

Needs numpy and Pillow (Termux: pkg install python-numpy python-pillow).

Usage:
  rr3_livery.py extract IN.etc.dds.z OUT.png
  rr3_livery.py import ORIGINAL.etc.dds.z IN.png OUT.etc.dds.z
"""
import argparse
import struct
import sys
import zlib

import numpy as np
from PIL import Image

TABLES = np.array([[2, 8], [5, 17], [9, 29], [13, 42],
                   [18, 60], [24, 80], [33, 106], [47, 183]], dtype=np.int32)
# Modifier for pixel index value (msb << 1 | lsb): +a, +b, -a, -b
MODS = np.stack([TABLES[:, 0], TABLES[:, 1], -TABLES[:, 0], -TABLES[:, 1]], axis=1)  # (8, 4)


def unpack_z(data):
    size = struct.unpack_from('<I', data)[0]
    dds = zlib.decompress(data[4:])
    if len(dds) != size:
        sys.exit('size header %d does not match data %d' % (size, len(dds)))
    return dds


def pack_z(dds):
    return struct.pack('<I', len(dds)) + zlib.compress(dds, 9)


def parse_dds(dds):
    if dds[:4] != b'DDS ':
        sys.exit('not a DDS file')
    height, width = struct.unpack_from('<II', dds, 12)
    mips = struct.unpack_from('<I', dds, 28)[0] or 1
    fourcc = dds[84:88]
    if fourcc != b'ETC ':
        sys.exit('unsupported texture format %r (only ETC1 "ETC ")' % fourcc)
    return width, height, mips


def level_sizes(width, height, mips):
    out = []
    for i in range(mips):
        w, h = max(1, width >> i), max(1, height >> i)
        out.append((w, h, ((w + 3) // 4) * ((h + 3) // 4) * 8))
    return out


# ---- ETC1 decode ----

def decode_etc1(blob, w, h):
    bw, bh = (w + 3) // 4, (h + 3) // 4
    hi = np.frombuffer(blob, dtype='>u4', count=bw * bh * 2)[0::2].astype(np.int64)
    lo = np.frombuffer(blob, dtype='>u4', count=bw * bh * 2)[1::2].astype(np.int64)
    diff = (hi >> 1) & 1
    flip = hi & 1
    t1 = (hi >> 5) & 7
    t2 = (hi >> 2) & 7
    base = np.zeros((len(hi), 2, 3), dtype=np.int32)
    for c, shift in enumerate((24, 16, 8)):
        # individual: 4 + 4 bits
        a4 = (hi >> (shift + 4)) & 15
        b4 = (hi >> shift) & 15
        # differential: 5 bits + signed 3 bit delta
        a5 = (hi >> (shift + 3)) & 31
        d3 = (hi >> shift) & 7
        d3 = np.where(d3 >= 4, d3 - 8, d3)
        b5 = (a5 + d3) & 31
        base[:, 0, c] = np.where(diff == 1, (a5 << 3) | (a5 >> 2), a4 * 17)
        base[:, 1, c] = np.where(diff == 1, (b5 << 3) | (b5 >> 2), b4 * 17)
    out = np.zeros((len(hi), 4, 4, 3), dtype=np.int32)  # [block, y, x, c]
    for x in range(4):
        for y in range(4):
            i = x * 4 + y
            idx = ((lo >> (i + 16)) & 1) * 2 + ((lo >> i) & 1)
            sub = np.where(flip == 1, (y >= 2), (x >= 2)).astype(np.int64)
            table = np.where(sub == 1, t2, t1)
            mod = MODS[table, idx]
            out[:, y, x, :] = base[np.arange(len(hi)), sub] + mod[:, None]
    out = np.clip(out, 0, 255).astype(np.uint8)
    img = out.reshape(bh, bw, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 3)
    return img[:h, :w]


# ---- ETC1 encode ----

def _sub_error(px, base):
    """px (N, 8, 3), base (N, 3) -> best table (N,), its error (N,), indices (N, 8)."""
    best_err = None
    for t in range(8):
        cand = np.clip(base[:, None, None, :] + MODS[t][None, None, :, None], 0, 255)  # (N,1,4,3)
        err = ((cand - px[:, :, None, :]) ** 2).sum(-1)  # (N, 8, 4)
        idx = err.argmin(-1)
        e = np.take_along_axis(err, idx[..., None], -1)[..., 0].sum(-1)
        if best_err is None:
            best_err, best_t, best_idx = e, np.zeros_like(e), idx
        else:
            better = e < best_err
            best_err = np.where(better, e, best_err)
            best_t = np.where(better, t, best_t)
            best_idx = np.where(better[:, None], idx, best_idx)
    return best_t, best_err, best_idx


# pixel order inside each half for flip 0 (left/right) and flip 1 (top/bottom); (y, x)
HALVES = {
    0: [[(y, x) for x in (0, 1) for y in range(4)], [(y, x) for x in (2, 3) for y in range(4)]],
    1: [[(y, x) for x in range(4) for y in (0, 1)], [(y, x) for x in range(4) for y in (2, 3)]],
}


def _encode_chunk(blocks):
    """blocks (N, 4, 4, 3) int32 -> (N,) packed 64-bit words as two uint32 (hi, lo)."""
    n = len(blocks)
    cands = []
    for flip in (0, 1):
        px = [np.stack([blocks[:, y, x] for y, x in HALVES[flip][s]], 1) for s in (0, 1)]
        avg = [p.mean(1) for p in px]
        q4 = [np.clip(np.rint(a * 15 / 255), 0, 15).astype(np.int32) for a in avg]
        q5 = [np.clip(np.rint(a * 31 / 255), 0, 31).astype(np.int32) for a in avg]
        d = q5[1] - q5[0]
        diff_ok = ((d >= -4) & (d <= 3)).all(1)
        for diff in (0, 1):
            bases = [(q << 3) | (q >> 2) for q in q5] if diff else [q * 17 for q in q4]
            r = [_sub_error(px[s], bases[s]) for s in (0, 1)]
            err = r[0][1] + r[1][1]
            if diff:
                err = np.where(diff_ok, err, np.iinfo(np.int64).max)
            cands.append(dict(err=err, flip=flip, diff=diff, q4=q4, q5=q5, r=r))
    pick = np.stack([c['err'] for c in cands]).argmin(0)
    choice = [(c, pick == k) for k, c in enumerate(cands)]
    hi = np.zeros(n, dtype=np.uint64)
    lo = np.zeros(n, dtype=np.uint64)
    for c, mask in choice:
        if not mask.any():
            continue
        m = mask
        h = np.zeros(m.sum(), dtype=np.uint64)
        if c['diff']:
            a, b = c['q5'][0][m], c['q5'][1][m]
            dl = (b - a) & 7
            for ch, shift in enumerate((24, 16, 8)):
                h |= (a[:, ch].astype(np.uint64) << np.uint64(shift + 3)) | (dl[:, ch].astype(np.uint64) << np.uint64(shift))
        else:
            a, b = c['q4'][0][m], c['q4'][1][m]
            for ch, shift in enumerate((24, 16, 8)):
                h |= (a[:, ch].astype(np.uint64) << np.uint64(shift + 4)) | (b[:, ch].astype(np.uint64) << np.uint64(shift))
        h |= c['r'][0][0][m].astype(np.uint64) << np.uint64(5)
        h |= c['r'][1][0][m].astype(np.uint64) << np.uint64(2)
        h |= np.uint64(c['diff'] << 1 | c['flip'])
        l = np.zeros(m.sum(), dtype=np.uint64)
        for s in (0, 1):
            idx = c['r'][s][2][m]  # (k, 8)
            for j, (y, x) in enumerate(HALVES[c['flip']][s]):
                i = x * 4 + y
                v = idx[:, j].astype(np.uint64)
                l |= ((v >> np.uint64(1)) << np.uint64(i + 16)) | ((v & np.uint64(1)) << np.uint64(i))
        hi[m], lo[m] = h, l
    return hi, lo


def encode_etc1(img):
    """img (h, w, 3) uint8 -> ETC1 bytes."""
    h, w = img.shape[:2]
    ph, pw = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    if (ph, pw) != (h, w):
        img = np.pad(img, ((0, ph - h), (0, pw - w), (0, 0)), mode='edge')
    blocks = img.reshape(ph // 4, 4, pw // 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 4, 4, 3).astype(np.int32)
    out = np.zeros(len(blocks) * 2, dtype='>u4')
    step = 8192
    for i in range(0, len(blocks), step):
        hi, lo = _encode_chunk(blocks[i:i + step])
        words = np.empty(len(hi) * 2, dtype=np.uint64)
        words[0::2] = hi & np.uint64(0xffffffff)
        words[1::2] = lo
        out[i * 2:(i + len(hi)) * 2] = words.astype(np.uint32)
    return out.tobytes()


# ---- commands ----

def cmd_extract(args):
    dds = unpack_z(open(args.src, 'rb').read())
    w, h, mips = parse_dds(dds)
    img = decode_etc1(dds[128:], w, h)
    Image.fromarray(img, 'RGB').save(args.png)
    print('%s: %dx%d ETC1, %d mip levels -> %s' % (args.src, w, h, mips, args.png))


def cmd_import(args):
    orig = unpack_z(open(args.original, 'rb').read())
    w, h, mips = parse_dds(orig)
    sizes = level_sizes(w, h, mips)
    if 128 + sum(s for _, _, s in sizes) != len(orig):
        sys.exit('original has unexpected size %d; not touching it' % len(orig))
    src = Image.open(args.png).convert('RGB')
    if src.size != (w, h):
        print('note: resizing %dx%d -> %dx%d (the livery must match the car UV layout)' % (src.size + (w, h)))
        src = src.resize((w, h), Image.LANCZOS)
    parts = [orig[:128]]
    for lw, lh, size in sizes:
        level = src if (lw, lh) == (w, h) else src.resize((lw, lh), Image.LANCZOS)
        data = encode_etc1(np.asarray(level, dtype=np.uint8))
        assert len(data) == size
        parts.append(data)
        print('  level %dx%d' % (lw, lh))
    dds = b''.join(parts)
    open(args.out, 'wb').write(pack_z(dds))
    err = np.abs(decode_etc1(dds[128:], w, h).astype(int) - np.asarray(src, dtype=int)).mean()
    print('wrote %s (%d bytes); mean error vs PNG: %.1f / 255' % (args.out, len(dds), err))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('extract', help='livery .etc.dds.z -> PNG')
    e.add_argument('src')
    e.add_argument('png')
    e.set_defaults(func=cmd_extract)
    i = sub.add_parser('import', help='PNG -> livery .etc.dds.z (header copied from the original)')
    i.add_argument('original')
    i.add_argument('png')
    i.add_argument('out')
    i.set_defaults(func=cmd_import)
    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
