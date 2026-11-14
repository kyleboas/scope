"""Build livedata/ils.json, the world's ILS and localizers, matched to OurAirports' runways (run again to refresh).

    python3 -I tools/build_ils.py nav.dat.gz [livedata/ils.json]

nav.dat.gz is Robin A. Peel's navaid database in X-Plane 810 form, under the GNU GPL v2 or later, as FlightGear ships it:
  https://gitlab.com/flightgear/fgdata/-/raw/next/Navaids/nav.dat.gz   (data cycle 2013.10, the last GPL release)
Run tools/build_airports.py first: a localizer is matched to a runway end by where it is and which way it points, not
by the runway's name, so a runway renumbered since 2013 still gets its ILS.

Writes {ICAO: {runway end: [kind, ident, mhz, course true, lat, lon, glideslope deg or 0]}}, kind ILS, LOC, LDA, SDF or IGS.
"""
import gzip
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from scope.core import gc_brg, gc_nm  # noqa: E402


def kind_of(name, has_gs):
    for k in ("LDA", "SDF", "IGS"):
        if name.startswith(k):
            return k
    return "ILS" if name.startswith("ILS") or has_gs else "LOC"


def adiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "livedata", "ils.json")
    aps = json.load(open(os.path.join(HERE, "livedata", "airports.json"), encoding="utf-8"))
    by_id = {a[0].upper(): a for a in aps}
    grid = {}                                   # 1° cells, for localizers whose airport code isn't OurAirports'
    for a in aps:
        if a[9]:
            grid.setdefault((int(math.floor(a[5])), int(math.floor(a[6]))), []).append(a)

    locs, gs = [], {}
    with gzip.open(src, "rt", encoding="latin-1") as f:
        for line in f:
            p = line.split()
            if len(p) < 11 or p[0] not in ("4", "5", "6"):
                continue
            lat, lon, mhz, hdg = float(p[1]), float(p[2]), int(p[4]) / 100, float(p[6])
            ap, rwy, name = p[8].upper(), p[9], " ".join(p[10:])
            if p[0] == "6":                      # glideslope: heading field is angle * 100000 + course
                gs[(ap, rwy, mhz)] = int(hdg // 1000) / 100
            else:
                locs.append((lat, lon, mhz, hdg % 360, p[7], ap, rwy, name))

    res, matched = {}, 0
    for lat, lon, mhz, crs, ident, ap, rwy, name in locs:
        cands = [by_id[ap]] if ap in by_id and by_id[ap][9] else []
        if not cands:
            cy, cx = int(math.floor(lat)), int(math.floor(lon))
            cands = [a for dy in (-1, 0, 1) for dx in (-1, 0, 1) for a in grid.get((cy + dy, cx + dx), []) if gc_nm(lat, lon, a[5], a[6]) < 6]
        best = None
        for a in cands:
            for r in a[9]:
                for end, (tla, tlo), (ola, olo) in ((r[0], r[2:4], r[4:6]), (r[1], r[4:6], r[2:4])):
                    if not end:
                        continue
                    h = gc_brg(tla, tlo, ola, olo)              # the runway's heading landing on this end
                    da = adiff(crs, h)
                    d = gc_nm(lat, lon, tla, tlo)
                    if da > 25 or d > 6 or d < 0.05:
                        continue
                    back = gc_brg(lat, lon, tla, tlo)           # the threshold must lie behind the antenna
                    if adiff(back, crs + 180) > 60:
                        continue
                    xt = abs(math.asin(max(-1, min(1, math.sin(d / 3440.065) * math.sin(math.radians(back - crs - 180)))))) * 3440.065
                    if xt > 1.5:
                        continue
                    score = xt + da / 10 - (0.5 if end.upper() == rwy.upper() else 0)
                    if best is None or score < best[0]:
                        best = (score, a[0], end)
        if not best:
            continue
        g = gs.get((ap, rwy, mhz), 0)
        k = kind_of(name, bool(g))
        row = [k, ident, mhz, round(crs, 1), round(lat, 5), round(lon, 5), g]
        ends = res.setdefault(best[1], {})
        if best[2] in ends and (ends[best[2]][0] == "ILS" or k != "ILS"):   # two on one end: keep the ILS
            continue
        ends[best[2]] = row
        matched += 1
    with open(out, "w") as f:
        json.dump(res, f, separators=(",", ":"), sort_keys=True)
    print(f"{len(locs)} localizers, {matched} matched to runway ends at {len(res)} airports")


if __name__ == "__main__":
    main()
