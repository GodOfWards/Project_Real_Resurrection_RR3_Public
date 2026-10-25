#!/usr/bin/env python3
"""Build tables/car-index.csv from a decrypted cardesc.list (see rr3_nct.py).

vehicles/data/cardesc.list.nct is only a list of car description file names,
u32 LE length + "<id>_<year>_<make>_<model>.bin". The readable name, make and
model below are derived from that file name; the game's own translated names
and the Road/Motorsport split live in files we do not have.

Formula 1 cars are named by chassis only, so the team is filled in from the
chassis code (RB = Red Bull, SF = Ferrari, ...). Formula E entries keep the
team as written in the file name.

Usage:
  rr3_car_index.py CARDESC_LIST OUT_CSV
"""
import csv
import re
import sys

MAKES = {  # file-name make -> display make; multi-word makes first
    "alfa_romeo": "Alfa Romeo", "aston_martin": "Aston Martin",
    "automobili_pininfarina": "Automobili Pininfarina", "formula_1": "Formula 1",
    "formula_e": "Formula E", "bmw": "BMW", "ktm": "KTM", "mclaren": "McLaren",
    "srt": "SRT",
}
UPPER = {"ss", "rs", "gt", "gts", "gtr", "gt-r", "srt", "amg", "sls", "rsr", "lms",
         "lfa", "nascar", "dtm", "bmw", "alms", "fia", "acr-x", "nsx-r", "is-f", "zr1",
         "r.s.", "lm", "gte", "gtd", "gtlm", "ds", "nsx", "rt", "sti", "wrx", "dpi-vr",
         "ac", "tdf", "fxx-k", "xjr", "rx", "dbr", "evo", "rc", "gti", "tcr", "nio",
         "e-tense", "ev", "csl", "gtb", "gto", "rss", "vip", "hpd", "arx", "jr", "drs",
         "mkiv", "eq", "f1", "rp", "gtc", "ccxr", "lp", "lpi", "tt", "sl", "slr", "clk", "wrc",
         "sv", "svr", "xe", "fd", "fkp", "trc", "st", "xr", "xxr", "lmdh", "tdi", "sto",
         "rxc", "js", "bc", "ii", "vi", "ff", "xl", "id", "lmp2", "lmp3", "dc2", "ek9", "scv12"}
SPECIAL = {"sdrive35is": "sDrive35is", "e-tron": "e-tron", "m40i": "M40i", "esports": "Esports",
           "mp4": "MP4", "x": "X", "z.e.16": "Z.E.16"}
LOWER = {"with", "de", "of", "the", "and", "for", "e", "la"}
F1_TEAMS = [  # chassis prefix -> team (longest prefix wins)
    ("academy", ""), ("amg_gt-r_safety", ""), ("esports", ""), ("valente", ""),
    ("r.s.", "Renault"), ("a5", "Alpine"), ("rb", "Red Bull"),
    ("str", "Toro Rosso"), ("at", "AlphaTauri"), ("vcarb", "RB"), ("sf", "Ferrari"),
    ("f1-75", "Ferrari"), ("w1", "Mercedes"), ("f1_w1", "Mercedes"), ("vf", "Haas"),
    ("c3", "Alfa Romeo"), ("c4", "Alfa Romeo"), ("c44", "Sauber"), ("mcl", "McLaren"),
    ("rp", "Racing Point"), ("amr", "Aston Martin"), ("fw", "Williams"),
]


def word(w, i):
    if w in SPECIAL:
        return SPECIAL[w]
    if "-" in w and w not in UPPER and not re.search(r"\d", w):
        return "-".join(word(x, j) for j, x in enumerate(w.split("-")))
    if w in UPPER or (re.search(r"\d", w) and not re.fullmatch(r"\d+(st|nd|rd|th)", w)):
        return w.upper()
    if w in LOWER and i:
        return w
    return w[:1].upper() + w[1:]


def pretty(s):
    """'lp_700-4_(z34)' -> 'LP 700-4 (Z34)'."""
    out = []
    for i, w in enumerate(s.strip("_").split("_")):
        pre, core, post = re.fullmatch(r"(\(?)(.*?)(\)?)", w).groups()
        out.append(pre + word(core, i) + post)
    return " ".join(out)


def split(slug):
    """'2009_nissan_370z_(z34)' -> (year, make, model)."""
    year, rest = slug.split("_", 1)
    for k in sorted(MAKES, key=len, reverse=True):
        if rest.startswith(k + "_"):
            return year, MAKES[k], rest[len(k) + 1:]
    make, model = rest.split("_", 1)
    return year, make.capitalize(), model


def team(model):
    best = max((p for p, _ in F1_TEAMS if model.startswith(p)), key=len, default=None)
    return dict(F1_TEAMS)[best] if best else ""


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    data = open(sys.argv[1], "rb").read()
    rows = []
    for m in re.finditer(rb"(\d+)_(\d{4}_[^\x00-\x1f]*?)\.bin", data):
        cid, slug = int(m.group(1)), m.group(2).decode()
        year, make, model = split(slug)
        t = team(model) if make == "Formula 1" else ""
        name = f"{year} {make} {pretty(model)}" + (f" ({t})" if t else "")
        rows.append((cid, year, make, pretty(model), t, name, f"{cid}_{slug}.bin"))
    rows.sort()
    assert len({r[0] for r in rows}) == len(rows), "duplicate car ids"
    with open(sys.argv[2], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["car_id", "name", "year", "make", "model", "team", "file"])
        w.writerows((r[0], r[5], r[1], r[2], r[3], r[4], r[6]) for r in rows)
    print(f"wrote {len(rows)} cars to {sys.argv[2]}")


if __name__ == "__main__":
    main()
