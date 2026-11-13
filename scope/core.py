"""The shared scope core: geometry, airports and runways (OurAirports), US procedures (FAA CIFP) and
airport ground maps (OpenStreetMap). Every site (livescope, ifscope, ...) uses these; a site's own
traffic code lives in its own repo.
"""
import gzip
import json
import math
import os
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # the repo root
R_NM = 3440.065


def gc_nm(lat1, lon1, lat2, lon2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_NM * math.asin(min(1.0, math.sqrt(h)))


def gc_brg(lat1, lon1, lat2, lon2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    return (math.degrees(math.atan2(math.sin(dl) * math.cos(p2), math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) + 360) % 360


def gc_dest(lat, lon, brg, nm):
    p1, l1, th, dr = math.radians(lat), math.radians(lon), math.radians(brg), nm / R_NM
    p2 = math.asin(math.sin(p1) * math.cos(dr) + math.cos(p1) * math.sin(dr) * math.cos(th))
    l2 = l1 + math.atan2(math.sin(th) * math.sin(dr) * math.cos(p1), math.cos(dr) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180



class Airports:
    """[ident, iata, name, city, country, lat, lon, elev, kind L/M/S/W, runways[[le, he, lat1, lon1, lat2, lon2, width_ft]],
    frequencies[[type, description, mhz]]]"""
    def __init__(self):
        path = os.path.join(HERE, "livedata", "airports.json")
        self.all = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
        self.major = [a[:9] for a in self.all if a[8] in "LM"]
        self.by_id = {a[0].upper(): a for a in self.all}

    def area(self, lat, lon, nm):
        nm = min(nm, 150)
        dlat = nm / 60
        dlon = nm / (60 * max(0.05, math.cos(math.radians(lat))))
        out = []
        for a in self.all:
            if abs(a[5] - lat) > dlat or abs(((a[6] - lon + 540) % 360) - 180) > dlon:
                continue
            d = gc_nm(lat, lon, a[5], a[6])
            if d <= nm:
                out.append((("LMSW".index(a[8]), d), a))
        out.sort(key=lambda t: t[0])
        return [a[:10] for _, a in out[:600]]

    def one(self, ident):
        return self.by_id.get(ident.strip().upper())

    def search(self, q):
        q = q.strip().upper()
        if not q:
            return []
        rank = []
        for a in self.all:
            ident, iata, name, city = a[0].upper(), (a[1] or "").upper(), a[2].upper(), (a[3] or "").upper()
            if q in (ident, iata):
                r = 0
            elif ident.startswith(q):
                r = 1
            elif q in name or q in city:
                r = 2
            else:
                continue
            rank.append((r, "LMSW".index(a[8]), a))
        rank.sort(key=lambda t: t[:2])
        return [a[:9] for _, _, a in rank[:15]]



class Ground:
    """Airport ground maps (taxiways with their letters, taxilanes, aprons, terminals, gates, hold lines) from
    OpenStreetMap through the Overpass API (ODbL), fetched the first time someone looks at an airport (one
    query at a time; they take up to a minute) and kept in livedata/ground/ for 30 days."""
    URL = "https://overpass-api.de/api/interpreter"
    KINDS = "taxiway|taxilane|apron|terminal|parking_position|holding_position"
    TTL = 30 * 86400

    def __init__(self, airports):
        self.airports = airports
        self.dir = os.environ.get("SCOPE_GROUND_DIR") or os.path.join(HERE, "livedata", "ground")
        self.lock = threading.Lock()
        self.queue, self.failed = [], {}
        self.wake = threading.Event()
        threading.Thread(target=self.worker, daemon=True).start()

    def path(self, ident):
        return os.path.join(self.dir, ident + ".json.gz")

    def query(self, sel):
        q = f'[out:json][timeout:90];{sel}(nwr{{AREA}}["aeroway"~"^({self.KINDS})$"];);out geom;'
        return q

    def overpass(self, q):
        data = urllib.parse.urlencode({"data": q}).encode()
        req = urllib.request.Request(self.URL, data=data, headers={"User-Agent": "scope/1 (+https://github.com/kyleboas/scope)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r).get("elements") or []

    def build(self, ident):
        a = self.airports.by_id.get(ident)
        if not a:
            return None
        els = self.overpass(self.query(f'area["icao"="{ident}"]["aeroway"="aerodrome"]->.a;').replace("{AREA}", "(area.a)"))
        if not els:
            els = self.overpass(self.query("").replace("{AREA}", f"(around:3500,{a[5]},{a[6]})"))
        r5 = lambda g: [[round(p["lat"], 5), round(p["lon"], 5)] for p in g if p]   # noqa: E731
        out = {"tw": [], "tl": [], "ap": [], "tm": [], "pp": [], "hp": []}
        for e in els:
            t = e.get("tags") or {}
            k = t.get("aeroway")
            ref = t.get("ref") or t.get("name") or ""
            if e["type"] == "node":
                if k == "parking_position":
                    out["pp"].append([ref, round(e["lat"], 5), round(e["lon"], 5)])
                continue
            if e["type"] == "way":
                rings = [r5(e.get("geometry") or [])]
            else:                                   # multipolygon relation: its outer rings
                rings = [r5(m.get("geometry") or []) for m in e.get("members") or [] if m.get("role") in ("outer", "") and m.get("type") == "way"]
            for g in rings:
                if len(g) < 2:
                    continue
                if k == "taxiway":
                    out["tw"].append([ref, g])
                elif k == "taxilane":
                    out["tl"].append([ref, g])
                elif k == "apron":
                    out["ap"].append(g)
                elif k == "terminal":
                    out["tm"].append([t.get("name") or "", g])
                elif k == "holding_position":
                    out["hp"].append(g)
                elif k == "parking_position":
                    c = g[len(g) // 2]
                    out["pp"].append([ref, c[0], c[1]])
        return out

    def worker(self):
        while True:
            self.wake.wait()
            with self.lock:
                ident = self.queue[0] if self.queue else None
                if ident is None:
                    self.wake.clear()
                    continue
            try:
                g = self.build(ident)
                if g is not None:
                    os.makedirs(self.dir, exist_ok=True)
                    tmp = self.path(ident) + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(gzip.compress(json.dumps(g, separators=(",", ":")).encode(), 6))
                    os.replace(tmp, self.path(ident))
            except Exception:  # noqa: BLE001 - Overpass busy or down: try again later
                self.failed[ident] = time.time()
            with self.lock:
                self.queue.remove(ident)
            time.sleep(2)

    def get(self, ident):
        """(gzipped json, None) when we have it, else (None, state) and it's queued"""
        ident = ident.strip().upper()
        if ident not in self.airports.by_id:
            return None, "unknown"
        p = self.path(ident)
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < self.TTL:
            with open(p, "rb") as f:
                return f.read(), None
        with self.lock:
            if time.time() - self.failed.get(ident, 0) < 600:
                return None, "failed"
            if ident not in self.queue:
                if len(self.queue) >= 20:
                    return None, "busy"
                self.queue.append(ident)
                self.wake.set()
            return None, "pending"



class Procs:
    """US SIDs, STARs and approaches (FAA CIFP via tools/build_procs.py): {ICAO: {"p": [...], "f": {...}}}"""
    def __init__(self, airports):
        path = os.path.join(HERE, "livedata", "procs.json")
        self.by_id = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        self.where = []
        for ident, d in self.by_id.items():
            a = airports.by_id.get(ident)
            p = (a[5], a[6]) if a else next((r[3] or r[4])[0] for r in d["p"])
            if p:
                self.where.append((ident, p[0], p[1]))
        self.cache = {}

    def area(self, lat, lon, nm, want=""):
        """the procedures of the airports within nm (nearest 40), plus `want` wherever it is"""
        nm = min(nm, 120)
        near = sorted((gc_nm(lat, lon, la, lo), i) for i, la, lo in self.where if abs(la - lat) < nm / 60 + 0.1 and gc_nm(lat, lon, la, lo) <= nm)
        ids = [i for _, i in near[:40]]
        want = want.strip().upper()
        if want in self.by_id and want not in ids:
            ids.append(want)
        return {i: self.by_id[i] for i in ids}


