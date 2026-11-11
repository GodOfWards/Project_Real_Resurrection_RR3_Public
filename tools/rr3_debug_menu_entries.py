#!/usr/bin/env python3
"""List every debug menu entry of a lib and whether its menu shows it
(issue #215). Part of Project Real Resurrection's work on Real Racing 3.
Not affiliated with, endorsed or supported by Electronic Arts.

For a lib patched by rr3_debug_menu.py --limited (any trim version), or a
full / develified one (everything is shown). It reads, it never writes.

How: in an arm64 emulator (unicorn: `python3 -m pip install unicorn`) it
  1. runs the label initializer _INIT_48 (0xe19598): the 317 static labels
     (0x1f9d6d8) and their handlers (0x1e78b70), numbered as in
     analysis/debug-menu.md (e.g. 15 = Character|Unlock + Own Everything);
  2. passes each label to the lib's own AddCheat (0xe266d8), so whatever
     filter the lib holds (trim v1, v2, later) decides: `kept` = the menu
     gets a button, `hidden` = it gets none.
Entries added at run time by the Setup*Cheats calls (Character|Wallet,
Time submenu, Time Trials|WTT|..., Web Browser, ...) are not in that table.
`--runtime` also lists the label strings in .rodata that start with a known
category and are not static labels: these are templates (the game may add
text, e.g. a wallet name), and in a trimmed lib they only appear if the
setup call that adds them still runs (see rr3_debug_menu.py, part trim).
It does not show how the menu looks; only a test in game does.

Usage:
  python3 tools/rr3_debug_menu_entries.py LIB [--kept] [--category Character] [--runtime]
"""
import argparse
import gzip
import struct
import sys

LABELS, HANDLERS, COUNT = 0x1F9D6D8, 0x1E78B70, 317
INIT = 0xE19598
ADD_CHEAT, RESUME = 0xE266D8, 0xE266DC
PLT = {0x1E17B20: "atexit", 0x1E17B40: "new", 0x1E17B70: "chk", 0x1E17C40: "memset"}
RET = 0xDEAD0
HEAP, STACK = 0x30000000, 0x40000000


def load(path):
    data = open(path, "rb").read()
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def segments(d):
    """(vaddr, offset, filesz) of each PT_LOAD, and the RELATIVE relocations."""
    phoff, = struct.unpack_from("<Q", d, 0x20)
    shoff, = struct.unpack_from("<Q", d, 0x28)
    phnum, = struct.unpack_from("<H", d, 0x38)
    shnum, = struct.unpack_from("<H", d, 0x3C)
    loads = []
    for i in range(phnum):
        t, _, off, va, _, fs = struct.unpack_from("<IIQQQQ", d, phoff + 56 * i)
        if t == 1:
            loads.append((va, off, fs))
    rel = []
    for i in range(shnum):
        _, t, _, _, off, size, _, _, _, ent = struct.unpack_from("<IIQQQQIIQQ", d, shoff + 64 * i)
        if t == 4 and ent == 24:                               # SHT_RELA
            for j in range(size // 24):
                r_off, info, add = struct.unpack_from("<QQq", d, off + 24 * j)
                if info & 0xFFFFFFFF == 1027:                  # R_AARCH64_RELATIVE
                    rel.append((r_off, add))
    return loads, rel


def emulator(d):
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn import arm64_const as R
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(0, 0x2000000)
    loads, rel = segments(d)
    for va, off, fs in loads:
        mu.mem_write(va, d[off:off + fs])
    for off, add in rel:
        mu.mem_write(off, struct.pack("<q", add))
    mu.mem_map(HEAP, 0x1000000)
    mu.mem_map(STACK, 0x100000)
    heap = [HEAP]

    def plt(uc, addr, size, _):
        k = PLT.get(addr)
        if k is None:
            return
        if k == "new":
            n = uc.reg_read(R.UC_ARM64_REG_X0)
            uc.reg_write(R.UC_ARM64_REG_X0, heap[0])
            heap[0] += (n + 15) & ~15
        elif k == "memset":
            a, v, n = (uc.reg_read(x) for x in (R.UC_ARM64_REG_X0, R.UC_ARM64_REG_X1, R.UC_ARM64_REG_X2))
            uc.mem_write(a, bytes([v & 0xFF]) * n)
        elif k == "chk":
            raise RuntimeError("stack check failed in the label initializer")
        uc.reg_write(R.UC_ARM64_REG_PC, uc.reg_read(R.UC_ARM64_REG_X30))

    mu.hook_add(UC_HOOK_CODE, plt, begin=0x1E17000, end=0x1E18000)
    return mu, R, heap


def read_str(mu, a):
    b = bytes(mu.mem_read(a, 24))
    if b[0] & 1:                                               # libc++ long string
        n, p = struct.unpack_from("<QQ", b, 8)
        return bytes(mu.mem_read(p, n)).decode("latin1")
    return b[1:1 + (b[0] >> 1)].decode("latin1")


def static_entries(mu, R):
    mu.reg_write(R.UC_ARM64_REG_SP, STACK + 0x80000)
    mu.reg_write(R.UC_ARM64_REG_X30, RET)
    mu.emu_start(INIT, RET)
    out = []
    for i in range(COUNT):
        h, = struct.unpack("<Q", mu.mem_read(HANDLERS + 16 * i, 8))
        out.append((i, h, read_str(mu, LABELS + 24 * i)))
    return out


def shown(mu, R, heap, label):
    """True if the lib's AddCheat goes on to add the entry (no filter, or kept)."""
    menu, s = heap[0], heap[0] + 0x1000
    b = label.encode("latin1")
    txt = s + 0x40
    heap[0] += 0x2000 + len(b)
    mu.mem_write(menu, b"\0" * 0x600)
    mu.mem_write(txt, b + b"\0")
    mu.mem_write(s, struct.pack("<QQQ", (len(b) + 16) | 1, len(b), txt))   # long form: works for any length
    mu.mem_write(menu + 0x4E8, struct.pack("<I", 41))
    mu.reg_write(R.UC_ARM64_REG_X0, menu)
    mu.reg_write(R.UC_ARM64_REG_X1, s)
    mu.reg_write(R.UC_ARM64_REG_SP, STACK + 0x80000)
    mu.reg_write(R.UC_ARM64_REG_X30, RET)
    pc = ADD_CHEAT
    for _ in range(4000):
        mu.emu_start(pc, 0, count=1)
        pc = mu.reg_read(R.UC_ARM64_REG_PC)
        if pc in (RESUME, RET):
            break
    if pc == RESUME:
        return True
    if pc == RET:
        return False
    raise RuntimeError(f"AddCheat did not finish for {label!r}")


def runtime_labels(d, static, categories):
    seen = {lab for _, _, lab in static}
    end = segments(d)[0][0][2]                                 # strings sit in the first (R E) segment
    out = []
    for chunk in d[:end].split(b"\0"):
        if b"|" in chunk and 4 < len(chunk) < 120:
            try:
                s = chunk.decode("ascii")
            except UnicodeDecodeError:
                continue
            if s.replace("\n", " ").isprintable() and s.split("|")[0] in categories and s not in seen:
                out.append(s)
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lib")
    ap.add_argument("--kept", action="store_true", help="list only the entries that get a button")
    ap.add_argument("--category", help="only this category (text before the first |), e.g. Character")
    ap.add_argument("--runtime", action="store_true", help="also the run-time label templates (see above)")
    a = ap.parse_args()
    try:
        import unicorn  # noqa: F401
    except ImportError:
        sys.exit("needs unicorn: python3 -m pip install unicorn")
    d = load(a.lib)
    mu, R, heap = emulator(d)
    static = static_entries(mu, R)
    if static[15][2] != "Character|Unlock + Own Everything":
        sys.exit("labels don't match the v14.0.1 develified build")

    def want(lab):
        return not a.category or lab.split("|")[0] == a.category

    n_kept = 0
    for i, h, lab in static:
        if not want(lab):
            continue
        k = shown(mu, R, heap, lab)
        n_kept += k
        if k or not a.kept:
            print(f"{i:3}  {'kept  ' if k else 'hidden'}  {h:#09x}  {lab!r}")
    if a.runtime:
        cats = {lab.split("|")[0] for _, _, lab in static} | {"Web Browser"}
        print("\nrun-time label templates (added by Setup*Cheats calls, if those run):")
        for lab in runtime_labels(d, static, cats):
            if not want(lab):
                continue
            k = shown(mu, R, heap, lab)
            if k or not a.kept:
                print(f"  -  {'kept  ' if k else 'hidden'}  {'':9}  {lab!r}")
    print(f"\n{n_kept} static entries kept")


if __name__ == "__main__":
    main()
