"""Build web/geo/airspace.json, the US Class B, C and D airspace around airports, for the Airspace layer (run again each
56-day cycle to refresh).

    python3 -I tools/build_airspace.py B.json C.json D.json [web/geo/airspace.json]

Each file is one class from the FAA's Class Airspace feature service (U.S. Government work, public domain), as GeoJSON:
  https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/Class_Airspace/FeatureServer/0/query
    ?where=LOCAL_TYPE%3D%27CLASS_B%27&outFields=*&outSR=4326&resultRecordCount=2000&f=geojson   (and CLASS_C, CLASS_D)
Not for navigation.

Writes [[airport, class, floor, ceiling, label lat, label lon, [ring as flat [lon, lat, ...], ...]], ...], one per shelf, with
the floor and ceiling in hundreds of feet MSL (floor 0: the surface). Outlines are simplified to about 0.05 nm and the label
goes at the point inside the shelf furthest from its edges (so a ring-shaped shelf is labelled on the ring, not in the hole).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOL = 0.0008                                           # degrees of latitude, about 0.05 nm


def simplify(pts, tol):
    """Ramer-Douglas-Peucker on [lon, lat] points (lon scaled by cos lat), keeping the first and last."""
    if len(pts) < 4:
        return pts
    k = math.cos(math.radians(pts[0][1]))
    keep, stack = [0, len(pts) - 1], [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay, bx, by = pts[a][0] * k, pts[a][1], pts[b][0] * k, pts[b][1]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy)
        best, bi = -1, -1
        for i in range(a + 1, b):
            px, py = pts[i][0] * k - ax, pts[i][1] - ay
            d = abs(dx * py - dy * px) / n if n else math.hypot(px, py)
            if d > best:
                best, bi = d, i
        if best > tol:
            keep.append(bi)
            stack += [(a, bi), (bi, b)]
    return [pts[i] for i in sorted(keep)]


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy))) if dx or dy else 0
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def label_point(rings):
    """The point inside the polygon (outer ring, holes) furthest from every edge, on a grid then refined around the best."""
    k = math.cos(math.radians(rings[0][0][1]))
    rs = [[(x * k, y) for x, y in r] for r in rings]
    xs, ys = [p[0] for p in rs[0]], [p[1] for p in rs[0]]

    def score(x, y):
        inside, d = False, 1e9
        for r in rs:
            for (ax, ay), (bx, by) in zip(r, r[1:] + r[:1]):
                if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                    inside = not inside
                d = min(d, seg_dist(x, y, ax, ay, bx, by))
        return d if inside else -1

    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    best = (-1, (x0 + x1) / 2, (y0 + y1) / 2)
    n = 14
    for _ in range(3):
        sx, sy = (x1 - x0) / n, (y1 - y0) / n
        for i in range(n + 1):
            for j in range(n + 1):
                x, y = x0 + i * sx, y0 + j * sy
                s = score(x, y)
                if s > best[0]:
                    best = (s, x, y)
        _, bx, by = best
        x0, x1, y0, y1 = bx - 2 * sx, bx + 2 * sx, by - 2 * sy, by + 2 * sy
    return round(best[2], 4), round(best[1] / k, 4)


def hundreds(v, code):
    return 0 if code == "SFC" or not v else round(v / 100)


def main(*args):
    srcs, dst = list(args), os.path.join(HERE, "web", "geo", "airspace.json")
    if srcs and srcs[-1].endswith("airspace.json"):
        dst = srcs.pop()
    out = []
    for src in srcs:
        for f in json.load(open(src, encoding="utf-8"))["features"]:
            p, g = f["properties"], f["geometry"]
            if not g or p.get("CLASS") not in ("B", "C", "D"):
                continue
            for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
                rings = []
                for r in poly:
                    r = [(x, y) for x, y in r]
                    if r[0] == r[-1]:
                        r = r[:-1]
                    r = simplify(r + r[:1], TOL)[:-1]
                    if len(r) >= 3:
                        rings.append(r)
                if not rings:
                    continue
                la, lo = label_point(rings)
                apt = p.get("ICAO_ID") or p.get("IDENT") or ""
                out.append([apt, p["CLASS"], hundreds(p["LOWER_VAL"], p["LOWER_CODE"]), hundreds(p["UPPER_VAL"], p["UPPER_CODE"]),
                            la, lo, [[round(c, 4) for x, y in r for c in (x, y)] for r in rings]])
    out.sort(key=lambda a: ("BCD".index(a[1]), a[0], a[2]))
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(out)} shelves, {sum(len(r) // 2 for a in out for r in a[6])} points -> {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:])
