"""livescope (livescope.kyleboas.com): real traffic anywhere on a STARS-style globe, watch only.

Traffic comes from public ADS-B aggregators (readsb JSON, at most 250 nm around a point), cached
per area so everyone looking at the same place shares one upstream request. Airports and
runways are OurAirports' (livedata/airports.json, built by tools/build_livescope.py). server.py serves
it all.
US airports' SIDs, STARs and approaches come from FAA CIFP (livedata/procs.json, tools/build_procs.py).
"""
import gzip
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = (("adsb.lol", "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"),
           ("adsb.fi", "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}"))
MAX_NM = 250
FRESH_S = 2.0          # an area's traffic is refetched at most this often
GAP_S = 0.4            # and upstream requests are spaced at least this far apart overall
EMERG = ("7500", "7600", "7700")
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


def area_key(lat, lon, nm):
    nm = next(b for b in (15, 30, 60, 120, 180, MAX_NM) if nm <= b or b == MAX_NM)
    step = 0.1 if nm <= 30 else 0.25 if nm <= 60 else 0.5 if nm <= 120 else 1.0
    lat = max(-89.0, min(89.0, round(lat / step) * step))
    lon = (round(lon / step) * step + 540) % 360 - 180
    return round(lat, 3), round(lon, 3), nm


def convert(a, now, lat0, lon0):
    lat, lon = a.get("lat"), a.get("lon")
    if lat is None or lon is None or (a.get("seen_pos") or 0) > 60:
        return None
    ground = a.get("alt_baro") == "ground"
    alt = a.get("alt_geom", 0) if ground else a.get("alt_baro", a.get("alt_geom"))
    if not isinstance(alt, (int, float)):
        alt = 0 if ground else None
    if alt is None:
        return None
    sq = a.get("squawk") or ""
    em = a.get("emergency") or "none"
    emer = sq if sq in EMERG else (em.upper() if em != "none" else "")
    hexid = (a.get("hex") or "").lower()
    cs = (a.get("flight") or "").strip() or a.get("r") or hexid.upper()
    return {"id": hexid or cs, "cs": cs, "hex": hexid, "lat": round(lat, 5), "lon": round(lon, 5), "alt": int(alt),
            "gs": round(a.get("gs") or 0), "hdg": round(a.get("track", a.get("true_heading", 0)) or 0, 1),
            "vs": int(a.get("baro_rate", a.get("geom_rate", 0)) or 0), "type": a.get("t") or "", "reg": a.get("r") or "",
            "sq": sq, "air": not ground, "ground": ground, "emer": emer, "cat": a.get("category") or "",
            "ts": round(now - (a.get("seen_pos") or 0), 2), "dist": round(gc_nm(lat0, lon0, lat, lon), 1)}


class Traffic:
    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}            # key -> (monotonic time, state)
        self.last = -1e9

    def fetch(self, lat, lon, nm):
        for name, url in SOURCES:
            try:
                req = urllib.request.Request(url.format(lat=lat, lon=lon, nm=nm), headers={"User-Agent": "livescope/1"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    d = json.load(r)
                now = d.get("now") or time.time()
                return name, d.get("ac") or d.get("aircraft") or [], now / 1000 if now > 1e11 else now   # ms (adsb.lol) or s (adsb.fi)
            except Exception:  # noqa: BLE001 - try the next source
                continue
        return None, None, None

    def get(self, lat, lon, nm):
        key = area_key(lat, lon, nm)
        with self.lock:
            hit = self.cache.get(key)
            if hit and time.monotonic() - hit[0] < FRESH_S:
                return hit[1]
            wait = self.last + GAP_S - time.monotonic()
            if wait > 0:
                if hit:
                    return hit[1]
                time.sleep(wait)
            self.last = time.monotonic()
            src, acs, now = self.fetch(*key)
            if acs is None:
                st = {**(hit[1] if hit else {"aircraft": [], "t": time.time(), "src": None}), "ok": False}
            else:
                seen = {}
                for o in (convert(a, now, key[0], key[1]) for a in acs):
                    if o and (o["id"] not in seen or o["ts"] > seen[o["id"]]["ts"]):
                        seen[o["id"]] = o
                st = {"ok": True, "t": now, "src": src, "center": [key[0], key[1]], "nm": key[2], "aircraft": list(seen.values())}
            self.cache[key] = (time.monotonic(), st)
            if len(self.cache) > 64:
                for k in sorted(self.cache, key=lambda k: self.cache[k][0])[:16]:
                    del self.cache[k]
            return st


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


class Atis:
    """Current ATIS for an airport: the FAA's D-ATIS text through atis.info (US airports that have it),
    plus the latest METAR from aviationweather.gov for any airport. Fetched when asked, kept a few minutes."""
    UA = {"User-Agent": "livescope/1 (livescope.kyleboas.com)"}

    def __init__(self):
        self.cache, self.lock = {}, threading.Lock()
        self.locks = {}

    def fetch(self, url):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=self.UA), timeout=8) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            return [] if e.code == 404 else None
        except Exception:  # noqa: BLE001 - a feed being down just means no ATIS shown
            return None

    def get(self, ident):
        ident = ident.upper()
        if not re.fullmatch(r"[A-Z0-9]{3,4}", ident):
            return {"atis": [], "metar": None}
        with self.lock:
            lk = self.locks.setdefault(ident, threading.Lock())
        with lk:
            now = time.time()
            c = self.cache.get(ident) or {}
            if "atis" not in c or now > c["atisT"]:
                atis = None
                if ident[0] in "KPT" and len(ident) == 4:
                    d = self.fetch("https://atis.info/api/" + ident)
                    if isinstance(d, list):
                        atis = [{"type": x.get("type") or "", "code": x.get("code") or "", "text": x.get("datis") or "",
                                 "time": x.get("time") or ""} for x in d if isinstance(x, dict) and x.get("datis")]
                else:
                    atis = []
                c["atis"] = atis if atis is not None else c.get("atis", [])
                c["atisT"] = now + (180 if atis else 900 if atis == [] else 60)
            if "metar" not in c or now > c["metarT"]:
                d = self.fetch("https://aviationweather.gov/api/data/metar?format=json&ids=" + ident)
                m = d[0] if isinstance(d, list) and d and isinstance(d[0], dict) else None
                c["metar"] = {"raw": m.get("rawOb") or "", "cat": m.get("fltCat") or "", "t": m.get("obsTime")} if m else c.get("metar")
                c["metarT"] = now + (300 if d is not None else 60)
            self.cache[ident] = c
            return {"atis": c["atis"], "metar": c["metar"]}


class Ground:
    """Airport ground maps (taxiways with their letters, taxilanes, aprons, terminals, gates, hold lines) from
    OpenStreetMap through the Overpass API (ODbL), fetched the first time someone looks at an airport (one
    query at a time; they take up to a minute) and kept in livedata/ground/ for 30 days."""
    URL = "https://overpass-api.de/api/interpreter"
    KINDS = "taxiway|taxilane|apron|terminal|parking_position|holding_position"
    TTL = 30 * 86400

    def __init__(self, airports):
        self.airports = airports
        self.dir = os.path.join(HERE, "livedata", "ground")
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
        req = urllib.request.Request(self.URL, data=data, headers={"User-Agent": "livescope/1 (livescope.kyleboas.com)"})
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


class World:
    """Every aircraft on Earth (airborne and on the ground) for the zoomed-out globe, from OpenSky's /states/all (the free ADS-B
    feeds above only answer for 250 nm around a point). Anonymous use allows ~100 snapshots a day, so one
    every 15 minutes; with a free OpenSky API client (OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET in the
    environment) one every 90 s. Fetched only while someone is looking, shared by everyone."""
    URL = "https://opensky-network.org/api/states/all"
    TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

    def __init__(self):
        self.lock = threading.Lock()
        self.cid, self.secret = os.environ.get("OPENSKY_CLIENT_ID"), os.environ.get("OPENSKY_CLIENT_SECRET")
        self.every = 90 if self.cid else 900
        self.body = json.dumps({"ok": False, "t": 0, "every": self.every, "ac": []}).encode()
        self.gz = gzip.compress(self.body)
        self.next_at = 0.0
        self.busy = False
        self.prev, self.lost = {}, {}
        self.token, self.token_exp = None, 0.0

    def auth(self):
        if not self.cid:
            return {}
        if time.time() > self.token_exp - 60:
            data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.cid, "client_secret": self.secret}).encode()
            with urllib.request.urlopen(urllib.request.Request(self.TOKEN_URL, data=data), timeout=10) as r:
                j = json.load(r)
            self.token, self.token_exp = j["access_token"], time.time() + j.get("expires_in", 1800)
        return {"Authorization": "Bearer " + self.token}

    def fetch(self):
        wait = self.every
        try:
            req = urllib.request.Request(self.URL, headers={"User-Agent": "livescope/1", **self.auth()})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
            t = d.get("time") or time.time()
            ac = []
            for st in d.get("states") or []:
                if st[5] is None or st[6] is None or not st[3] or t - st[3] > (600 if st[8] else 120):
                    continue
                alt = 0 if st[8] else st[7] if st[7] is not None else st[13]
                ac.append([st[0], round(st[6], 4), round(st[5], 4), round(st[10] or 0), round((st[9] or 0) * 1.94384),
                           round((alt or 0) * 3.28084 / 100), int(st[3]), (st[1] or "").strip(), 1 if st[8] else 0])
            est = self.estimate(t, ac)
            body = json.dumps({"ok": True, "t": t, "every": self.every, "src": "OpenSky", "ac": ac, "est": est}, separators=(",", ":")).encode()
            gz = gzip.compress(body, 6)
            with self.lock:
                self.body, self.gz = body, gz
        except urllib.error.HTTPError as e:
            retry = e.headers.get("X-Rate-Limit-Retry-After-Seconds") if e.headers else None
            wait = max(self.every, int(retry)) if retry and retry.isdigit() else self.every
        except Exception:  # noqa: BLE001 - try again next time round
            wait = 120
        with self.lock:
            self.next_at = time.time() + wait
            self.busy = False

    def estimate(self, t, ac):
        """Aircraft that were cruising and then dropped out of every receiver's range (mostly over the oceans,
        where there's no free ADS-B): carried on toward their scheduled destination (adsbdb route, when it fits
        their track) or straight on, at their last ground speed. A guess, drawn as such; dropped when the
        aircraft is seen again, reaches its destination, comes over an area with coverage, or after 4 hours
        without a route (13 with one)."""
        seen = {r[0] for r in ac}
        cells = {}
        for r in ac:
            if not r[8]:
                k = (int(r[1] // 2), int(r[2] // 2))
                cells[k] = cells.get(k, 0) + 1
        for hx, r in self.prev.items():
            if hx not in seen and hx not in self.lost and not r[8] and r[5] >= 200 and r[4] >= 250:
                self.lost[hx] = {"cs": r[7], "lat": r[1], "lon": r[2], "trk": r[3], "gs": r[4], "alt": r[5], "ts": r[6]}
        self.prev = {r[0]: r for r in ac}
        routes = ROUTES.get([v["cs"] for v in self.lost.values() if v["cs"]], background=True)
        out = []
        for hx in list(self.lost):
            v = self.lost[hx]
            dt = t - v["ts"]
            if hx in seen or dt > 13 * 3600:
                del self.lost[hx]
                continue
            dist = v["gs"] * dt / 3600
            rt, to = routes.get((v["cs"] or "").upper()), ""
            if rt and rt[4] is not None and rt[5] is not None:
                left = gc_nm(v["lat"], v["lon"], rt[4], rt[5])
                if left > 150 and abs((gc_brg(v["lat"], v["lon"], rt[4], rt[5]) - v["trk"] + 540) % 360 - 180) < 50:
                    if dist >= left - 40:                # it has got there (or nearly: it'll be seen on approach)
                        del self.lost[hx]
                        continue
                    to = rt[3]
                    la, lo = gc_dest(v["lat"], v["lon"], gc_brg(v["lat"], v["lon"], rt[4], rt[5]), dist)
                    trk = gc_brg(la, lo, rt[4], rt[5])
            if not to:
                if dt > 4 * 3600:
                    del self.lost[hx]
                    continue
                la, lo = gc_dest(v["lat"], v["lon"], v["trk"], dist)
                la2, lo2 = gc_dest(v["lat"], v["lon"], v["trk"], dist + 10)
                trk = gc_brg(la, lo, la2, lo2)
            if dt > 1200 and cells.get((int(la // 2), int(lo // 2)), 0) >= 3:   # receivers there would see it
                del self.lost[hx]
                continue
            out.append([hx, round(la, 3), round(lo, 3), round(trk), v["gs"], v["alt"], int(t), v["cs"], to, int(v["ts"])])
        return out

    def get(self):
        with self.lock:
            if not self.busy and time.time() >= self.next_at:
                self.busy = True
                threading.Thread(target=self.fetch, daemon=True).start()
            return self.body, self.gz


class Routes:
    """Scheduled routes by callsign from adsbdb.com (crowd-sourced, so sometimes out of date: the page only
    believes one when the aircraft's position and climb/descent fit it). Looked up in the background,
    a few a second, and kept for 6 hours (unknown callsigns for 1)."""
    URL = "https://api.adsbdb.com/v0/callsign/{}"
    TTL, TTL_NONE, PER_S = 6 * 3600, 3600, 4

    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}            # callsign -> (time, [orig, olat, olon, dest, dlat, dlon] or None)
        self.queue = []
        self.wake = threading.Event()
        threading.Thread(target=self.worker, daemon=True).start()

    def lookup(self, cs):
        req = urllib.request.Request(self.URL.format(cs), headers={"User-Agent": "livescope/1"})
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                fr = (json.load(r).get("response") or {}).get("flightroute")
        except urllib.error.HTTPError as e:
            return None if e.code == 404 else "retry"
        except Exception:  # noqa: BLE001 - network trouble: try again later
            return "retry"
        if not isinstance(fr, dict):
            return None
        o, d = fr.get("origin") or {}, fr.get("destination") or {}
        if not o.get("icao_code") or not d.get("icao_code"):
            return None
        return [o["icao_code"], o.get("latitude"), o.get("longitude"), d["icao_code"], d.get("latitude"), d.get("longitude")]

    def worker(self):
        while True:
            self.wake.wait()
            with self.lock:
                cs = self.queue.pop(0) if self.queue else None
                if not self.queue:
                    self.wake.clear()
            if cs is None:
                continue
            r = self.lookup(cs)
            with self.lock:
                if r == "retry":
                    self.cache.pop(cs, None)
                else:
                    self.cache[cs] = (time.time(), r)
            time.sleep(1 / self.PER_S)

    def get(self, callsigns, background=False):
        """known routes now; unknown ones are queued (a page's asks ahead of background ones) and show up on a later call"""
        now, out = time.time(), {}
        with self.lock:
            for cs in callsigns:
                cs = cs.strip().upper()
                if not cs.isalnum() or len(cs) > 8:
                    continue
                hit = self.cache.get(cs)
                if hit and hit[0] and now - hit[0] < (self.TTL if hit[1] else self.TTL_NONE):
                    out[cs] = hit[1]
                elif not (hit and hit[0] == 0):          # not already queued
                    self.cache[cs] = (0, None)
                    if background:
                        self.queue.append(cs)
                    else:
                        self.queue.insert(0, cs)
            if len(self.queue) > 3000:                    # too far behind: drop the background tail
                for cs in self.queue[3000:]:
                    self.cache.pop(cs, None)
                del self.queue[3000:]
            if self.queue:
                self.wake.set()
            if len(self.cache) > 50000:
                for k in [k for k, v in self.cache.items() if v[0] and now - v[0] > self.TTL_NONE]:
                    del self.cache[k]
        return out


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


TRAFFIC = Traffic()
AIRPORTS = Airports()
PROCS = Procs(AIRPORTS)
ROUTES = Routes()
WORLD = World()
GROUND = Ground(AIRPORTS)
ATIS = Atis()
