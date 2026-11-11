#!/usr/bin/env python3
"""Our logo on the start-up screens (no lib or APK change).

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

At start the game shows three loading screens, each a GUI layout
(analysis/splash-screen.md):

  1 LoadingScreen_Init      EA: Firemonkeys + Slingshot logos
  2 LoadingScreen_Firemint  EA: the same two logos
  3 LoadingScreen_R3        EA: "Real Racing 3" logo (symbol RealRacing3Logo,
                            glyph U+0032 of r3_symbols.ttf) + safety text

This tool writes the files that give them our logo:

  part init      LoadingScreen_Init.gui: the two logos -> RealRacing3Logo,
                 same box as screen 3; logo only
  part firemint  LoadingScreen_Firemint.gui: the two logos -> RealRacing3Logo
                 + our notice (label PRR_NOTICE, where screen 3 has its text);
                 loading icon where screen 3 has it
  part symbols   r3_symbols.ttf: U+0032 (RealRacing3Logo) -> our logo, so
                 screens 1-3 (and the download screen's small logo) show it
  part decal     r3_decals.ttf: U+00FC (a livery decal) -> our logo

Screen 3 keeps EA's layout: its logo comes from the font, its text stays.
The logo glyph is tools/prr-logo-glyph-v2.json (v1: prr-logo-glyph.json).
Inputs are EA's files as shipped (game/gui/, game/fonts/); each input's md5
is checked.

  build OUT [--parts init,firemint,symbols,decal] [--gui-dir D] [--font-dir D]
            [--glyph-version 2|1]
            writes OUT/gui/processed/LoadingScreen_Init.gui,
            OUT/gui/processed/LoadingScreen_Firemint.gui, OUT/r3_symbols.ttf,
            OUT/r3_decals.ttf: the game paths, so OUT can go into the asset
            update folder (rr3_cc_server.py --asset-update/--asset-test) or a
            phone's files/.depot/; --glyph-version 1 writes v1's logo
            (roll-back to the fonts served on 2026-11-08)
  check FILE...   says whether each file is EA's, ours (which version) or
                  something else
  show FILE.gui   prints a layout decrypted (XML)

The font parts need fontTools (pip install fonttools); the layout parts
need only Python 3.

v1 (2026-11-08, issue #462, docs/splash-logo.md): the four parts above.
Works in game (Tom, 2026-11-08): all four files of `build`, copied into
.depot/ by hand, then served to everyone from the server's assets/ folder;
the A15 (member 1000) downloaded all four and showed screens 1-3 as above.
v2 (2026-11-09, issue #518): the logo glyph with smooth curves
(prr-logo-glyph-v2.json, 34 contours, 3,835 points, from PR_Logo_Updated.zip)
in both fonts. Its 3,835 points are over r3_symbols.ttf's maxp.maxPoints
(1,902), so v2 raises that limit to the logo's count (v1 refused instead;
v1's glyph is under it, so --glyph-version 1 still gives v1's bytes). The
two layouts are v1's, unchanged. Untested in game.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rr3_nct  # noqa: E402

VERSION = "2"
LIB = os.path.join(HERE, "..", "game", "develified-libRealRacing3.so.gz")
GUI_DIR = os.path.join(HERE, "..", "game", "gui")
FONT_DIR = os.path.join(HERE, "..", "game", "fonts")
# Logo glyph per tool version; the layouts did not change in v2.
GLYPH_FILES = {"1": os.path.join(HERE, "prr-logo-glyph.json"),
               "2": os.path.join(HERE, "prr-logo-glyph-v2.json")}
GLYPH_FILE = GLYPH_FILES[VERSION]
PARTS = ("init", "firemint", "symbols", "decal")

NOTICE = ("Project Real Resurrection is a non-profit community project. "
          "Not affiliated with, endorsed or supported by Electronic Arts.")

# EA's files as shipped with the develified game data (Tom's phone, 2026-11-07).
EA_MD5 = {
    "LoadingScreen_Init.gui": "6aabccd1dc57774aba396132edd58bdc",      # apk/res (res.zip), asset_list_startup.txt
    "LoadingScreen_Firemint.gui": "dd3c5b521f58fb83f50916c860510305",  # .depot, asset_list_base_gui.txt
    "LoadingScreen_R3.gui": "632360c06c8a8f667c9f542692c5676f",        # .depot, asset_list_base_gui.txt
    "r3_symbols.ttf": "5df975f1b5a7de804f5fcec28ed10ddb",              # apk/res (res.zip), asset_list_startup.txt
    "r3_decals.ttf": "c5aa91e955ca494a9a26c2d1361e809d",               # apk/res (res.zip), asset_list_startup.txt
}
# What v1 writes (layouts: exact bytes; fonts: see font_is_ours, bytes depend on fontTools).
OURS_MD5 = {
    "LoadingScreen_Init.gui": {"v1": "d5c8d1ca1ead9cb1673ccfadac6550cb"},
    "LoadingScreen_Firemint.gui": {"v1": "5d54b680df8d20b52512907aa15efae0"},
}
# Earlier test files, recognised by check.
TEST_MD5 = {
    "d336b713d920538bf81c1d3b193854a8": "LoadingScreen_Init.gui test 2026-11-08 (logo + notice; replaced by v1, logo only)",
    "dd6a783f5eff1c5e2acfadf565493d92": "r3_symbols.ttf from PR3_Logo.zip (U+0032 = our logo; tested in game 2026-11-07)",
    "46fe119ce642de5ad87923bc8e23351a": "r3_decals.ttf from PR3_Logo.zip (U+00FC = our logo)",
    "d6ffd8b097482c337210a45838b21a19": ("r3_symbols.ttf from PR_Logo_Updated.zip (2026-11-09; source of glyph v2, "
                                         "not served: every glyph re-encoded, logo advance 1180)"),
}

GUI_PATH = "gui/processed/"
FONT_GLYPH = {"r3_symbols.ttf": 0x32, "r3_decals.ttf": 0xFC}

# The two logo labels inside LOADING_FRAME, as in EA's Init and Firemint
# layouts (the text between FIRST and the end of the Slingshot label).
LOGOS_FIRST = {"LoadingScreen_Init.gui": '\t\t\t<GuiSymbolLabel type="134" id="20005" symbol="FiremonkeyLogo"',
               "LoadingScreen_Firemint.gui": '\t\t\t<GuiSymbolLabel type="134" id="20006" symbol="FiremonkeyLogo"'}
LOGOS_LAST = 'symbol="Slingshot Logo"'
END_SYMBOL = "</GuiSymbolLabel>\n"

# Screen 3's logo label and text label (EA's LoadingScreen_R3), with an id
# of our choice; the text label is named PRR_NOTICE, not LOADING_TIP, so
# the loading screen code (0x1175720) does not put the safety text in it.
LOGO_LABEL = (
    '\t\t\t<GuiSymbolLabel type="134" id="{id}" symbol="RealRacing3Logo" r="255" g="255" b="255" alpha="1" '
    'resize_style="width_height" anchor="5" resizeRectWH="true" dropShadowColorR="0" dropShadowColorG="0" '
    'dropShadowColorB="0" dropShadowColorA="0" dropShadowOffsetX="0" dropShadowOffsetY="0" flipHorizontal="false" '
    'flipVertical="false">\n'
    '\t\t\t\t<GuiTransform x="0" xRel="true" xAspect="false" y="-0.0125" yRel="true" yAspect="false" width="0.9" '
    'widthRel="true" widthAspect="false" height="0.225" heightRel="true" heightAspect="false" child_anchor="Center" '
    'parent_anchor="Center" />\n'
    '\t\t\t</GuiSymbolLabel>\n')
NOTICE_LABEL = (
    '\t\t\t<GuiLabel type="11" id="{id}" id_string="PRR_NOTICE" text="{text}" font="Conduit_Medium" r="255" '
    'g="255" b="255" editor_only_text="false" anchor="1" wrapped="true" forceUppercase="false" wrapMode="WordWrap" '
    'leading="1" scrolling="false" anchorInBox="true" bestFitLineCount="4" bestFitResizeRect="false" '
    'measureWithLineHeight="false" strike_through="false" rotation="0" style="">\n'
    '\t\t\t\t<GuiTransform x="0" xRel="true" xAspect="false" y="0.764313" yRel="true" yAspect="false" '
    'width="0.776056" widthRel="true" widthAspect="false" height="0.15" heightRel="true" heightAspect="false" '
    'child_anchor="TopCenter" parent_anchor="TopCenter" />\n'
    '\t\t\t</GuiLabel>\n')
# Firemint's loading icon sits in the corner; screen 3 (and Init) keep it 1% in.
ICON_EA = ('<GuiTransform x="0" xRel="true" xAspect="false" y="0" yRel="true" yAspect="false" width="70" '
           'widthRel="false" widthAspect="false" height="70" heightRel="false" heightAspect="false" '
           'child_anchor="BottomRight" parent_anchor="BottomRight" />')
ICON_R3 = ICON_EA.replace('x="0"', 'x="-0.01"', 1).replace('y="0"', 'y="-0.01"', 1)


def md5(b):
    return hashlib.md5(b).hexdigest()


def read_checked(path, name):
    raw = open(path, "rb").read()
    if md5(raw) != EA_MD5[name]:
        raise ValueError(f"{path}: md5 {md5(raw)} is not EA's {name} ({EA_MD5[name]})")
    return raw


def decrypt(raw, lib):
    xml = rr3_nct.crypt(raw, lib)
    if not xml.startswith(b"<?xml"):
        raise ValueError("not a .gui layout (no XML after decryption)")
    return xml.decode("ascii")


def replace_logos(xml, name, new):
    """Replace the Firemonkeys + Slingshot labels inside LOADING_FRAME by new."""
    first = LOGOS_FIRST[name]
    if xml.count(first) != 1:
        raise ValueError(f"{name}: logo labels not found")
    a = xml.index(first)
    b = xml.index(END_SYMBOL, xml.index(LOGOS_LAST, a)) + len(END_SYMBOL)
    if xml.index("</GuiFadeFrame>") < b:
        raise ValueError(f"{name}: logo labels not inside LOADING_FRAME")
    return xml[:a] + new + xml[b:]


def make_init(ea_xml):
    return replace_logos(ea_xml, "LoadingScreen_Init.gui", LOGO_LABEL.format(id=20005))


def make_firemint(ea_xml):
    if ea_xml.count(ICON_EA) != 1:
        raise ValueError("LoadingScreen_Firemint.gui: loading icon not found")
    xml = ea_xml.replace(ICON_EA, ICON_R3)
    return replace_logos(xml, "LoadingScreen_Firemint.gui",
                         LOGO_LABEL.format(id=20006) + NOTICE_LABEL.format(id=20007, text=NOTICE))


def load_glyph(path=GLYPH_FILE):
    d = json.load(open(path))
    return d["contours"], d["advance"], d["lsb"]


def logo_glyph(contours):
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
    from fontTools.ttLib.tables import ttProgram
    from array import array
    g = Glyph()
    pts = [(x, y) for ct in contours for x, y, _ in ct]
    g.coordinates = GlyphCoordinates(pts)
    g.flags = array("B", [on for ct in contours for _, _, on in ct])
    ends, n = [], 0
    for ct in contours:
        n += len(ct)
        ends.append(n - 1)
    g.endPtsOfContours = ends
    g.numberOfContours = len(contours)
    g.program = ttProgram.Program()
    g.program.fromBytecode(b"")
    return g


def make_font(path, name, glyph_file=GLYPH_FILE):
    """EA's font with one glyph replaced by our logo; bytes of the result."""
    import io
    from fontTools.ttLib import TTFont
    read_checked(path, name)
    contours, adv, lsb = load_glyph(glyph_file)
    # recalcTimestamp=False keeps EA's head.modified (same input, same bytes);
    # recalcBBoxes=False keeps EA's stored glyph boxes (some are 1 unit off,
    # e.g. U+0111; fontTools would "fix" them and move those glyphs by 1 unit).
    f = TTFont(path, recalcTimestamp=False, recalcBBoxes=False)
    gname = f.getBestCmap()[FONT_GLYPH[name]]
    g = logo_glyph(contours)
    f["glyf"][gname] = g
    g.recalcBounds(f["glyf"])
    if g.xMin != lsb:
        raise ValueError("logo glyph: lsb does not match its xMin")
    f["hmtx"][gname] = (adv, lsb)
    # Without the recalc, keep the font-wide limits right by hand: maxp's
    # largest simple glyph is raised to the logo's if the logo is bigger
    # (v2 in r3_symbols.ttf: 3,835 points > 1,902).
    maxp, head, hhea = f["maxp"], f["head"], f["hhea"]
    maxp.maxPoints = max(maxp.maxPoints, len(g.coordinates))
    maxp.maxContours = max(maxp.maxContours, g.numberOfContours)
    if adv > hhea.advanceWidthMax:
        raise ValueError(f"{name}: logo advance is over hhea.advanceWidthMax")
    head.xMin, head.yMin = min(head.xMin, g.xMin), min(head.yMin, g.yMin)
    head.xMax, head.yMax = max(head.xMax, g.xMax), max(head.yMax, g.yMax)
    out = io.BytesIO()
    f.save(out, reorderTables=False)
    f.close()
    return out.getvalue()


def font_glyph_version(data, name):
    """The version of our logo glyph in the font, or None."""
    for v, path in sorted(GLYPH_FILES.items(), reverse=True):
        if font_is_ours(data, name, path):
            return v
    return None


def font_is_ours(data, name, glyph_file=GLYPH_FILE):
    """True if the font's logo glyph is the one in glyph_file (points, flags, advance)."""
    import io
    from fontTools.ttLib import TTFont
    f = TTFont(io.BytesIO(data))
    gname = f.getBestCmap().get(FONT_GLYPH[name])
    if gname is None:
        return False
    contours, adv, lsb = load_glyph(glyph_file)
    g = f["glyf"][gname]
    if g.isComposite() or g.numberOfContours != len(contours):
        return False
    c, ends, flags = g.getCoordinates(f["glyf"])
    want = [(x, y, on) for ct in contours for x, y, on in ct]
    got = [(int(x), int(y), fl & 1) for (x, y), fl in zip(c, flags)]
    return got == want and f["hmtx"][gname][0] == adv


def build(out, parts, gui_dir=GUI_DIR, font_dir=FONT_DIR, lib_path=LIB, glyph_version=VERSION):
    written = []
    lib = rr3_nct.read_lib(lib_path) if {"init", "firemint"} & set(parts) else None
    for part, name, maker in (("init", "LoadingScreen_Init.gui", make_init),
                              ("firemint", "LoadingScreen_Firemint.gui", make_firemint)):
        if part not in parts:
            continue
        xml = maker(decrypt(read_checked(os.path.join(gui_dir, name), name), lib))
        dst = os.path.join(out, GUI_PATH, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(rr3_nct.crypt(xml.encode("ascii"), lib))
        written.append(dst)
    for part, name in (("symbols", "r3_symbols.ttf"), ("decal", "r3_decals.ttf")):
        if part not in parts:
            continue
        data = make_font(os.path.join(font_dir, name), name, GLYPH_FILES[glyph_version])
        dst = os.path.join(out, name)
        os.makedirs(out, exist_ok=True)
        open(dst, "wb").write(data)
        written.append(dst)
    return written


def describe(path):
    data = open(path, "rb").read()
    h = md5(data)
    for n, m in EA_MD5.items():
        if h == m:
            return f"EA's {n}"
    for n, vs in OURS_MD5.items():
        for v, m in vs.items():
            if h == m:
                return f"ours: {n} {v}"
    if h in TEST_MD5:
        return "test file: " + TEST_MD5[h]
    if data[:4] in (b"\x00\x01\x00\x00", b"true"):
        try:
            ours = [(n, font_glyph_version(data, n)) for n in FONT_GLYPH]
        except ImportError:
            return "font (install fonttools to check its glyph)"
        ours = [(n, v) for n, v in ours if v]
        if ours:
            return " / ".join(f"ours: {n} with our logo glyph v{v} (U+{FONT_GLYPH[n]:04X})" for n, v in ours)
        return "font, not EA's, logo glyph not ours"
    return "unknown"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("out")
    b.add_argument("--parts", default=",".join(PARTS))
    b.add_argument("--gui-dir", default=GUI_DIR)
    b.add_argument("--font-dir", default=FONT_DIR)
    b.add_argument("--lib", default=LIB)
    b.add_argument("--glyph-version", default=VERSION, choices=sorted(GLYPH_FILES),
                   help="logo glyph to write in the fonts (default: %(default)s)")
    c = sub.add_parser("check")
    c.add_argument("files", nargs="+")
    s = sub.add_parser("show")
    s.add_argument("file")
    s.add_argument("--lib", default=LIB)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            parts = [p for p in a.parts.split(",") if p]
            bad = [p for p in parts if p not in PARTS]
            if bad or not parts:
                raise ValueError(f"--parts: unknown {bad}; choose from {','.join(PARTS)}")
            for p in build(a.out, parts, a.gui_dir, a.font_dir, a.lib, a.glyph_version):
                print(f"{md5(open(p, 'rb').read())}  {p}")
        elif a.cmd == "check":
            for p in a.files:
                print(f"{p}: {describe(p)}")
        else:
            sys.stdout.write(decrypt(open(a.file, "rb").read(), rr3_nct.read_lib(a.lib)))
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
