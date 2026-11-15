"""Build web/geo/centers.json, the world's Center airspaces (ARTCCs and FIRs), for the Center airspaces layer (run again to refresh).

    python3 -I tools/build_centers.py Boundaries.geojson [web/geo/centers.json]

Boundaries.geojson is the VATSpy Data Project's (VATSIM), under CC BY-SA 4.0:
  https://raw.githubusercontent.com/vatsimnetwork/vatspy-data-project/master/Boundaries.geojson
They follow the real-world boundaries closely but aren't official. Not for navigation.

Writes [[id, oceanic 0/1, label lat, label lon, [ring as flat [lon, lat, ...], ...]], ...], coordinates to 0.01° (about 0.6 nm).
A ring's points closer than that to the last one kept are dropped.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ring(pts):
    out = []
    for lon, lat in pts:
        p = [round(lon, 2), round(lat, 2)]
        if out[-2:] != p:
            out += p
    return out if len(out) >= 6 else None


def main(src, dst=os.path.join(HERE, "web", "geo", "centers.json")):
    feats = json.load(open(src, encoding="utf-8"))["features"]
    out = []
    for f in feats:
        p, g = f["properties"], f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = [r for poly in polys for r in (ring(x) for x in poly) if r]
        if rings:
            out.append([p["id"], int(p.get("oceanic") == "1"), round(float(p["label_lat"]), 2), round(float(p["label_lon"]), 2), rings])
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(out)} Center airspaces, {sum(len(r) // 2 for c in out for r in c[4])} points -> {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:])
