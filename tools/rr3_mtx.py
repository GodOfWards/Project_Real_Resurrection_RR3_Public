#!/usr/bin/env python3
"""Make real-money store purchases complete offline (v2) (libRealRacing3.so v14.0.1, arm64, develified build).

Part of Project Real Resurrection's work; not affiliated with Electronic Arts. Offsets are for develified.apk only (one APK for every GPU).

Develified flow: StoreMenu -> MTXManager::PurchaseStoreProduct (0xb84344) ->
NimbleMTX::PurchaseStoreProduct (0xb8d6e4) queues a Google Play transaction;
EA's server validates the receipt; only then NimbleMTX::AwardProduct
(0xb8f7b8) builds an RR3Product and calls MTXManager::AwardProduct
(0xb86174), which grants the pack and notifies the store screens.

Parts (all on by default, pick with --parts):

  open  Opening the store first refreshes the Google Play catalog and the
        player's past purchases; offline neither reports success, so the
        store shows "sign into a valid Google Play Store account".
        NimbleMTX::RefreshStoreCatalog (0xb90d8c) and
        RefreshStorePurchases (0xb9105c) now just call their callback with
        true and return.

  buy   NimbleMTX::PurchaseStoreProduct, from 0xb8d7a8: instead of queueing
        a Google Play transaction, build the RR3Product from the store
        product (0xcee2e0, as NimbleMTX::AwardProduct does) and call
        MTXManager::AwardProduct(mgr, product, storeProduct, 0, "", sku, "")
        directly, then fall through to the develified tail (0xb8d8dc).
  valid MTXManager's "is this product buyable" checks (0xb8436c, 0xb843a4)
        read StoreProduct+0x91, which is only set when Google Play returns a
        price for the SKU. Both now return true for any known product.
  list  The store lists NimbleMTX's validated products (static store data
        matched against the Google Play catalog), which is empty offline.
        NimbleMTX vtable slots 5 and 10 (count / get(i) of validated
        products) are pointed at slots 6 and 11 (the same for the static
        product list), by editing their R_AARCH64_RELATIVE addends.
  online (v2, issue #634) The Buy buttons run EA's connection check 0xcd80c0
        before MTXManager::PurchaseStoreProduct; with no network (a phone
        offline, or rr3_offline.py's Offline mode, which reports state 1)
        it shows a connection error and the purchase never starts. At the
        store Buy (0xee4e9c), the Purchase/Restore screen's Purchase
        (0xa09098) and a store item Pack Card (0xaf0618), `bl 0xcd80c0`
        becomes `mov w0, #1` (what the check returns when online; on
        success it never calls its callback). The store opening's fallback
        check when no pack is listed (0xee63b4, `bl 0xee6540`) becomes
        `mov w0, #1` too, so the store opens whatever the connection.
        Restore Purchases and every other screen keep EA's check.

Versions: v1 = open,buy,valid,list (build part `store`); v2 = v1 + online
(`store@v2`). `--version 1` writes v1; `check` reads both.

Usage:
  rr3_mtx.py check LIB
  rr3_mtx.py patch IN OUT [--parts open,buy,valid,list,online] [--version 1|2]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

BUY_SITE = 0xB8D7A8
BUY_DEVELIFIED = bytes.fromhex(
    "40040036680240f9e00313aa083140f900013fd600040036633240b9a1c7ffd0"
    "02c0ff9021700d9142881f914000805297060091d547149489024039280b4039"
    "200340798a0a40f9b6c2fff03f010072d6f62891001d70b3e3028a9a"
)
# Source in analysis/store-purchases.md; assembled with llvm-mc.
BUY_CODE = bytes.fromhex(
    "570400b4ff0305d1e0830091e1620291e2420091e30a40b9c8820594ff7f00a9"
    "ff0b00f9089f009008f946f9000140f9e1830091e20317aae3031f2ae4030091"
    "e50314aae603009161e2ff97e0830091fda5fa97ff03059137000014"
)
VALID_SITES = {0xB8436C: 0x39424428, 0xB843A4: 0x39424408}  # ldrb w8, [x1|x0, #0x91]
VALID_CODE = 0x52800028                                     # mov w8, #1
# .rela.dyn entries (file offset of r_addend) for NimbleMTX vtable 0x1e50b30.
LIST_SITES = {
    0x9C710 + 16: (0xB90308, 0xB9034C),  # slot 5: validated count -> static count
    0x9C788 + 16: (0xB9002C, 0xB90088),  # slot 10: validated[i] -> static[i]
}
OPEN_SITES = {
    0xB90D8C: bytes.fromhex("ff8302d1fd7b04a9fc6f05a9fa6706a9f85f07a9f65708a9"),
    0xB9105C: bytes.fromhex("ffc301d1fd7b04a9f65705a9f44f06a9fd03019156d03bd5"),
}
# callback(true); return  -- the callback is a std::function<void(bool)>
OPEN_CODE = bytes.fromhex(
    "fd7bbea9fd030091201040f9e00000b428008052e8430039e1430091080040f9"
    "081940f900013fd6fd7bc2a8c0035fd6"
)
# online: `bl` to EA's connection check -> mov w0, #1 (issue #634)
ONLINE_SITES = {
    0xEE4E9C: 0x97F7CC89,  # store Buy: bl 0xcd80c0
    0xA09098: 0x940B3C0A,  # Purchase/Restore screen, Purchase: bl 0xcd80c0
    0xAF0618: 0x94079EAA,  # store item (Pack Card) purchase: bl 0xcd80c0
    0xEE63B4: 0x94000063,  # store open with no pack listed: bl 0xee6540
}
ONLINE_CODE = 0x52800020                                   # mov w0, #1
PARTS = ("open", "buy", "valid", "list", "online")
VERSION = 2
VERSION_PARTS = {1: ["open", "buy", "valid", "list"], 2: list(PARTS)}


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def state(d):
    """Return {part: True (patched) / False (develified) / None (unrecognised)}."""
    s = {}
    o = [bytes(d[a:a + len(OPEN_CODE)]) for a in OPEN_SITES]
    s["open"] = (True if all(x == OPEN_CODE for x in o)
                 else False if all(x[:24] == st for x, st in zip(o, OPEN_SITES.values())) else None)
    b = bytes(d[BUY_SITE:BUY_SITE + len(BUY_CODE)])
    s["buy"] = True if b == BUY_CODE else False if b == BUY_DEVELIFIED else None
    v = [struct.unpack_from("<I", d, a)[0] for a in VALID_SITES]
    s["valid"] = (True if all(w == VALID_CODE for w in v)
                  else False if v == list(VALID_SITES.values()) else None)
    l = [(struct.unpack_from("<Q", d, o)[0], old, new) for o, (old, new) in LIST_SITES.items()]
    s["list"] = (True if all(w == new for w, _, new in l)
                 else False if all(w == old for w, old, _ in l) else None)
    w = [struct.unpack_from("<I", d, a)[0] for a in ONLINE_SITES]
    s["online"] = (True if all(x == ONLINE_CODE for x in w)
                   else False if w == list(ONLINE_SITES.values()) else None)
    return s


def show(s):
    return ", ".join(f"{p}: {'patched' if v else 'develified' if v is False else 'UNRECOGNISED'}"
                     for p, v in s.items())


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    All parts: 'store@v2'; v1's four parts: 'store'; others 'store=a+b'."""
    s = state(d)
    if None in s.values():
        return None
    on = [p for p, v in s.items() if v]
    if not on:
        return ""
    if on == VERSION_PARTS[2]:
        return "store@v2"
    if on == VERSION_PARTS[1]:
        return "store"
    return "store=" + "+".join(on)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--parts", help="default: every part of --version")
    p.add_argument("--version", type=int, choices=sorted(VERSION_PARTS), default=VERSION,
                   help="1: open,buy,valid,list; 2 (default): + online")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if a.cmd == "check":
        print("Store purchases:", show(s))
        return
    parts = ([x for x in a.parts.split(",") if x] if a.parts
             else VERSION_PARTS[a.version])
    bad = [x for x in parts if x not in PARTS]
    if bad:
        raise SystemExit(f"unknown part(s): {', '.join(bad)}; choose from {', '.join(PARTS)}")
    for x in parts:
        if s[x] is None:
            raise SystemExit(f"{x}: unrecognised code, refusing to patch ({show(s)})")
    if "open" in parts:
        for site in OPEN_SITES:
            d[site:site + len(OPEN_CODE)] = OPEN_CODE
    if "buy" in parts:
        d[BUY_SITE:BUY_SITE + len(BUY_CODE)] = BUY_CODE
    if "valid" in parts:
        for site in VALID_SITES:
            struct.pack_into("<I", d, site, VALID_CODE)
    if "list" in parts:
        for off, (_, new) in LIST_SITES.items():
            struct.pack_into("<Q", d, off, new)
    if "online" in parts:
        for site in ONLINE_SITES:
            struct.pack_into("<I", d, site, ONLINE_CODE)
    open(a.out, "wb").write(gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d))
    print(f"Store purchases: {show(state(d))}; wrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())
