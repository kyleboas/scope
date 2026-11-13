"""Every airport's SIDs, STARs and approaches from an FAA CIFP file, as lat/lon polylines for scope.

Usage (the CIFP file is untrusted data, read only as text):
    python3 -I tools/build_procs.py FAACIFP18 livedata/procs.json

FAA CIFP covers US airports (and a few US territories); other countries publish their procedures
under their own, mostly non-free, terms. Only legs that end at a fix are kept (plus RF arcs, drawn
round their centre); heading/course-to-altitude legs have no position and are skipped, so a
procedure is the line through its fixes. Written as
    {ICAO: {"p": [[kind, name, transition, [[lat, lon], ...], [[lat, lon], ...missed]], ...],
            "f": {fix: [lat, lon]}}}
kind is sid, star, approach or transition (an approach's feeder).
Column numbers are 1-based ARINC 424-18 columns.
"""
import json
import math
import re
import sys


def col(r, a, b=None):
    return r[a - 1:(b if b else a)]


def dms(t):
    t = t.strip()
    if len(t) < 9 or t[0] not in "NSEW":
        return None
    n = 2 if t[0] in "NS" else 3
    try:
        b = t[1:]
        v = int(b[:n]) + int(b[n:n + 2]) / 60 + (int(b[n + 2:n + 4]) + int(b[n + 4:] or 0) / 10 ** len(b[n + 4:])) / 3600
    except ValueError:
        return None
    return -v if t[0] in "SW" else v


def pos(r, a=33):
    la, lo = dms(col(r, a, a + 8)), dms(col(r, a + 9, a + 18))
    return None if la is None or lo is None else (la, lo)


APP_NAME = {"I": "ILS", "L": "LOC", "R": "RNAV (GPS)", "H": "RNAV (RNP)", "D": "VOR/DME", "V": "VOR", "S": "VOR",
            "N": "NDB", "Q": "NDB/DME", "P": "GPS", "B": "LOC/BC", "X": "LDA", "U": "SDF", "G": "IGS", "J": "GLS"}


def app_name(pid):
    """I28L -> ILS 28L, R10RZ -> RNAV (GPS) Z 10R, VDM-A -> VOR/DME-A"""
    kind = APP_NAME.get(pid[0], pid[0])
    rest = pid[1:].strip()
    if rest[:1] in "-":
        return kind + rest
    if rest[:1] == "D" and pid[0] in "VN":
        kind, rest = kind + "/DME", rest[1:]
    m = re.fullmatch(r"(\d\d[LRC]?)([A-Z]?)", rest)
    if not m:
        return f"{kind} {rest}".strip()
    rw, sfx = m.groups()
    return f"{kind}{' ' + sfx if sfx else ''} RWY {rw}"


def arc(c, p0, p1, turn):
    """points from p0 to p1 round centre c (lat/lon), turning L or R"""
    k = math.cos(math.radians(c[0]))
    v = lambda p: ((p[1] - c[1]) * k, p[0] - c[0])   # noqa: E731
    a0, a1 = math.atan2(*v(p0)[::-1]), math.atan2(*v(p1)[::-1])
    r0, r1 = math.hypot(*v(p0)), math.hypot(*v(p1))
    d = a1 - a0
    if turn == "R":                # clockwise in x/y = decreasing angle
        while d > 0:
            d -= 2 * math.pi
    else:
        while d < 0:
            d += 2 * math.pi
    n = max(2, int(abs(d) / math.radians(8)))
    out = []
    for i in range(1, n + 1):
        f = i / n
        a, r = a0 + d * f, r0 + (r1 - r0) * f
        out.append((c[0] + r * math.sin(a), c[1] + r * math.cos(a) / k))
    return out


def main(src, dst):
    recs = [ln.rstrip("\n") for ln in open(src, encoding="ascii", errors="replace") if ln.startswith("S") and len(ln) >= 120]
    enroute, vhf, ndb, term, tndb, rwy, loc, apt = {}, {}, {}, {}, {}, {}, {}, {}
    for r in recs:
        sec, sub = col(r, 5), col(r, 6)
        if sec == "E" and sub == "A":
            p = pos(r)
            if p:
                enroute[(col(r, 14, 18).strip(), col(r, 20, 21))] = p
        elif sec == "D" and sub == " " and col(r, 22) in "01":
            p = pos(r) or pos(r, 56)
            if p:
                vhf[(col(r, 14, 17).strip(), col(r, 20, 21))] = p
        elif sec == "D" and sub == "B" and col(r, 22) in "01":
            p = pos(r)
            if p:
                ndb[(col(r, 14, 17).strip(), col(r, 20, 21))] = p
        elif sec == "P" and col(r, 22) in "01":
            a, ss = col(r, 7, 10).strip(), col(r, 13)
            p = pos(r)
            if not p:
                continue
            if ss == "C":
                term[(a, col(r, 14, 18).strip())] = p
            elif ss == "N":
                tndb[(a, col(r, 14, 17).strip())] = p
            elif ss == "G":
                rwy[(a, col(r, 14, 18).strip())] = p
            elif ss == "I":
                loc[(a, col(r, 14, 17).strip())] = p
            elif ss == "A":
                apt[a] = p

    def resolve(a, ident, icao, section):
        if section == "PC":
            return term.get((a, ident)) or enroute.get((ident, icao))
        if section == "EA":
            return enroute.get((ident, icao)) or term.get((a, ident))
        if section == "D ":
            return vhf.get((ident, icao))
        if section == "DB":
            return ndb.get((ident, icao))
        if section == "PN":
            return tndb.get((a, ident)) or ndb.get((ident, icao))
        if section == "PG":
            return rwy.get((a, ident))
        if section == "PI":
            return loc.get((a, ident))
        if section == "PA":
            return apt.get(a)
        return None

    routes = {}          # (airport, kind, proc, rtype, transition) -> [(seq, legs...)]
    for r in recs:
        if col(r, 5) != "P" or col(r, 13) not in "DEF" or col(r, 39) not in "01":
            continue
        a = col(r, 7, 10).strip()
        key = (a, col(r, 13), col(r, 14, 19).strip(), col(r, 20), col(r, 21, 25).strip())
        routes.setdefault(key, []).append(r)

    out = {}
    for (a, sec, pid, rtype, trans), rs in routes.items():
        rs.sort(key=lambda r: col(r, 27, 29))
        pts, missed, fixes = [], [], {}
        cur = pts
        for r in rs:
            if col(r, 42) == "M" and cur is pts:
                cur = missed
                if pts:
                    missed.append(pts[-1])
            ident = col(r, 30, 34).strip()
            if not ident:
                continue
            p = resolve(a, ident, col(r, 35, 36), col(r, 37, 38))
            if not p:
                continue
            pt = col(r, 48, 49)
            if pt in ("RF", "AF") and cur:
                cid = col(r, 107, 111).strip() if pt == "RF" else col(r, 51, 54).strip()
                csec = col(r, 115, 116) if pt == "RF" else col(r, 79, 80)
                cicao = col(r, 113, 114) if pt == "RF" else col(r, 55, 56)
                c = resolve(a, cid, cicao, csec) if cid else None
                turn = col(r, 44)
                if c and turn in "LR":
                    cur.extend(arc(c, cur[-1], p, turn)[:-1])
            if not cur or cur[-1] != p:
                cur.append(p)
            if col(r, 37, 38) in ("PC", "EA", "D ", "DB", "PN"):
                fixes[ident] = p
        if len(pts) + len(missed) < 2:
            continue
        kind = {"D": "sid", "E": "star", "F": "approach"}[sec]
        if sec == "F" and rtype == "A":
            kind = "transition"
        name = app_name(pid) if sec == "F" else pid
        rnd = lambda q: [[round(x, 4), round(y, 4)] for x, y in q]   # noqa: E731
        ap = out.setdefault(a, {"p": [], "f": {}})
        ap["p"].append([kind, name, trans, rnd(pts), rnd(missed) if len(missed) > 1 else []])
        for n, p in fixes.items():
            ap["f"][n] = [round(p[0], 4), round(p[1], 4)]
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"{len(out)} airports, {sum(len(v['p']) for v in out.values())} routes -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
