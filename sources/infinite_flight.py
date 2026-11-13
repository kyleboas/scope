"""ifscope's data: Infinite Flight multiplayer traffic, ATC, ATIS and flight plans, from the Infinite Flight Live API (PublicApi v3, or a v2 API key).

Credentials (environment, server side only):
    IF_API_KEY                         a Live API v2 key (Bearer header, https://api.infiniteflight.com/public/v2), or
    IF_CLIENT_ID / IF_CLIENT_SECRET    a PublicApi v3 Confidential client with server-to-server access (approved by IF)
    IF_RPM                             requests per minute to allow ourselves (default 25: under the free limit of 30;
                                       raise to ~90 if the account that owns the key has Pro, limit 100)

Infinite Flight's API usage rules (https://infiniteflight.com/guide/developer-reference/api-rules/usage-and-data-rules)
are built in here:
  - one in-memory cache per request, replaced on refresh, never written to disk or logged, and dropped
    50 minutes after it was fetched (the rule is 1 hour);
  - minimum intervals: sessions 10 min, flights 15 s, ATC and world status 60 s, a flight's plan or route
    60 s and only when someone selects it, ATIS 60 s and only for the airport someone opens, reference
    data (aircraft and liveries) 60 min;
  - nothing is fetched unless a page asks for it, and the page stops asking after 15 minutes without
    user input, so polling stops when nobody is watching;
  - a 429 pauses every request for its Retry-After.
"""
import calendar
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from scope.core import gc_nm
from sources.adsb import Atis

API = os.environ.get("IF_API_BASE", "https://api.infiniteflight.com")   # override only for local tests
TOKEN_URL = API + "/auth/v2/connect/token"
UA = {"User-Agent": "ifscope/1", "Accept": "application/json"}
LIVE_MAX_AGE = 50 * 60         # drop any cached live response this old, whether or not anyone asked again
WORLDS = {1: "casual", 2: "training", 3: "expert"}
FREQ = {0: "Ground", 1: "Tower", 2: "Unicom", 3: "Clearance", 4: "Approach", 5: "Departure", 6: "Center", 7: "ATIS"}
UUID = re.compile(r"[0-9a-fA-F-]{36}")


class ApiError(Exception):
    pass


class Client:
    """Authenticated GETs within a requests-per-minute budget (one sliding minute, shared by everything)."""

    def __init__(self):
        self.key = os.environ.get("IF_API_KEY", "").strip()
        self.cid = os.environ.get("IF_CLIENT_ID", "").strip()
        self.secret = os.environ.get("IF_CLIENT_SECRET", "").strip()
        self.rpm = max(5, int(os.environ.get("IF_RPM", "25")))
        self.base = API + ("/public/v2" if self.key and not self.cid else "/public/v3")
        self.lock = threading.Lock()
        self.sent = []             # monotonic times of requests in the last minute
        self.paused_until = 0.0
        self.token, self.token_exp = None, 0.0
        self.last_error = ""

    @property
    def configured(self):
        return bool(self.key or (self.cid and self.secret))

    def auth(self):
        if self.cid and self.secret:
            if time.time() > self.token_exp - 120:   # one token for its whole 30 minutes, never one per request
                data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.cid,
                                               "client_secret": self.secret}).encode()
                try:
                    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data, headers=UA), timeout=15) as r:
                        j = json.load(r)
                except urllib.error.HTTPError as e:
                    try:
                        err = json.load(e).get("error", "")
                    except Exception:  # noqa: BLE001
                        err = ""
                    self.token_exp = time.time() + 300 - 120     # don't hammer the token endpoint: try again in 5 min
                    raise ApiError("not approved yet" if err == "unauthorized_client" else "bad client id or secret"
                                   if err == "invalid_client" else f"token endpoint said {e.code} {err}".strip())
                self.token, self.token_exp = j["access_token"], time.time() + int(j.get("expires_in", 1800))
            if not self.token:
                raise ApiError("no token")
            return {"Authorization": "Bearer " + self.token}
        return {"Authorization": "Bearer " + self.key}

    def budget(self, reserve):
        """take one request from the minute's budget, keeping `reserve` back for the flight lists"""
        with self.lock:
            now = time.monotonic()
            if now < self.paused_until:
                return False
            self.sent = [t for t in self.sent if now - t < 60]
            if len(self.sent) >= self.rpm - reserve:
                return False
            self.sent.append(now)
            return True

    def get(self, path, reserve=0):
        if not self.configured:
            raise ApiError("no API key")
        if not self.budget(reserve):
            raise ApiError("busy")
        try:
            req = urllib.request.Request(self.base + path, headers={**UA, **self.auth()})
            with urllib.request.urlopen(req, timeout=12) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = (e.headers.get("Retry-After") or "60") if e.headers else "60"
                with self.lock:
                    self.paused_until = time.monotonic() + (int(ra) if ra.isdigit() else 60)
                raise ApiError("rate limited")
            if e.code == 401 and self.cid:
                self.token_exp = 0
            self.last_error = f"HTTP {e.code}"
            raise ApiError(self.last_error)
        except ApiError:
            raise
        except Exception as e:  # noqa: BLE001 - network trouble
            self.last_error = type(e).__name__
            raise ApiError(self.last_error)
        if not isinstance(d, dict) or d.get("errorCode") not in (0, None):
            code = d.get("errorCode") if isinstance(d, dict) else "?"
            raise ApiError({4: "API key not authorised", 5: "server not found", 6: "flight not found",
                            7: "no ATIS"}.get(code, f"error {code}"))
        self.last_error = ""
        return d.get("result")


class Cached:
    """one cached response per key, kept for `every` seconds; refreshed only when asked for after that"""

    def __init__(self, client, every, reserve=4):
        self.c, self.every, self.reserve = client, every, reserve
        self.data = {}             # key -> (time.time() fetched, value)
        self.locks, self.lock = {}, threading.Lock()

    def get(self, key, path, convert=lambda x: x):
        with self.lock:
            lk = self.locks.setdefault(key, threading.Lock())
        with lk:
            hit = self.data.get(key)
            if hit and time.time() - hit[0] < self.every:
                return hit[1], hit[0], ""
            try:
                v = convert(self.c.get(path, self.reserve))
            except ApiError as e:
                return (hit[1], hit[0], str(e)) if hit else (None, 0, str(e))
            self.data[key] = (time.time(), v)
            return v, self.data[key][0], ""

    def expire(self, max_age):
        with self.lock:
            now = time.time()
            for k in [k for k, v in self.data.items() if now - v[0] > max_age]:
                del self.data[k]
            if len(self.locks) > 2000:
                self.locks.clear()


def parse_t(s):
    """'2020-10-02 00:46:19Z' (or ISO with T and fractions) -> unix seconds"""
    if not s:
        return 0.0
    try:
        return calendar.timegm(time.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return 0.0


# Infinite Flight aircraft names -> ICAO type designators for the scope's data blocks and list
TYPES = [(r"A-10", "A10"), (r"A220-100|A220-1", "BCS1"), (r"A220-300|A220", "BCS3"), (r"A318", "A318"), (r"A319", "A319"),
         (r"A320.*neo", "A20N"), (r"A320", "A320"), (r"A321.*neo", "A21N"), (r"A321", "A321"), (r"A330-200", "A332"),
         (r"A330-900|A330neo", "A339"), (r"A330", "A333"), (r"A340-600", "A346"), (r"A340", "A343"), (r"A350-1000", "A35K"),
         (r"A350", "A359"), (r"A380", "A388"), (r"717", "B712"), (r"737-700|737-7\b", "B737"), (r"737 MAX 8|737-8 MAX|MAX 8", "B38M"),
         (r"737-800|737-8", "B738"), (r"737-900|737-9", "B739"), (r"737-200", "B732"), (r"747-100", "B741"), (r"747-200", "B742"),
         (r"747SP", "B74S"), (r"747-400", "B744"), (r"747-8", "B748"), (r"757-200", "B752"), (r"757", "B752"),
         (r"767-300", "B763"), (r"767-200", "B762"), (r"767-400", "B764"), (r"777-200LR|777F", "B77L"), (r"777-200", "B772"),
         (r"777-300ER|777-300", "B77W"), (r"777X|777-9", "B779"), (r"787-8", "B788"), (r"787-9", "B789"), (r"787-10", "B78X"),
         (r"CRJ-?200", "CRJ2"), (r"CRJ-?700", "CRJ7"), (r"CRJ-?900", "CRJ9"), (r"CRJ-?1000", "CRJX"), (r"E175|E-175", "E175"),
         (r"E190|E-190", "E190"), (r"E195|E-195", "E195"), (r"Q400|Dash 8", "DH8D"), (r"ATR.?72", "AT76"), (r"ATR.?42", "AT45"),
         (r"172", "C172"), (r"208|Caravan", "C208"), (r"Citation X", "C750"), (r"Citation", "C25B"), (r"TBM", "TBM9"),
         (r"SR22", "SR22"), (r"XCub", "CUB"), (r"Cub", "J3"), (r"Concorde", "CONC"), (r"DC-10|KC-10", "DC10"), (r"MD-11", "MD11"),
         (r"MD-?8\d|MD-?90", "MD82"), (r"C-130|Hercules", "C130"), (r"C-17", "C17"), (r"F-14", "F14"), (r"F-16", "F16"),
         (r"F-18|F/A-18|Super Hornet", "F18S"), (r"F-22", "F22"), (r"F-35", "F35"), (r"Spitfire", "SPIT"), (r"B-?2\b|Spirit", "B2"),
         (r"P-38", "P38"), (r"E-?2 ?Hawkeye", "E2"), (r"Bell|407", "B407"), (r"H125|AS350", "AS50"), (r"Challenger 350", "CL35"),
         (r"Pilatus|PC-?12", "PC12"), (r"DA62", "DA62"), (r"DA42", "DA42"), (r"Decathlon", "BL8"), (r"Twin Otter|DHC-6", "DHC6")]


def type_code(name):
    for pat, code in TYPES:
        if re.search(pat, name or "", re.I):
            return code
    return (name or "").split(" ")[-1][:4].upper()


class Live:
    """Everything the page asks for, per Infinite Flight server (casual / training / expert)."""

    def __init__(self, airports):
        self.c = Client()
        self.airports = airports
        self.sessions = Cached(self.c, 600, reserve=0)
        self.flights = Cached(self.c, 15, reserve=0)          # the flight lists get the whole budget
        self.world = Cached(self.c, 60)
        self.atc = Cached(self.c, 60)
        self.plans = Cached(self.c, 60)
        self.routes = Cached(self.c, 60)
        self.atis = Cached(self.c, 60)
        self.liveries = Cached(self.c, 3600)
        self.conv = {}             # (server key, fetch time) -> converted flight list, so it's built once per fetch
        threading.Thread(target=self.janitor, daemon=True).start()

    def janitor(self):
        while True:
            time.sleep(60)
            for c in (self.sessions, self.flights, self.world, self.atc, self.plans, self.routes, self.atis):
                c.expire(LIVE_MAX_AGE)
            self.liveries.expire(2 * 3600)
            for k in [k for k in self.conv if time.time() - k[1] > LIVE_MAX_AGE]:
                self.conv.pop(k, None)

    # ---------------------------------------------------------------- servers
    def servers(self):
        v, t, err = self.sessions.get("s", "/sessions")
        out = []
        for s in v or []:
            key = WORLDS.get(s.get("worldType"))
            if key and not any(o["key"] == key for o in out):
                out.append({"key": key, "id": s["id"], "name": s.get("name") or key.title(), "users": s.get("userCount") or 0})
        out.sort(key=lambda o: ["casual", "training", "expert"].index(o["key"]))
        return out, err

    def session(self, key):
        srv, err = self.servers()
        s = next((o for o in srv if o["key"] == key), None) or next((o for o in srv if o["key"] == "expert"), None)
        return s, err

    def livery_names(self):
        v, _, _ = self.liveries.get("l", "/aircraft/liveries",
                                    lambda r: {x["id"]: (x.get("aircraftName") or "", x.get("liveryName") or "") for x in r or []})
        return v or {}

    # ---------------------------------------------------------------- flights
    def status(self, s):
        """world status: per-flight [origin, destination] from flight plans, and the open ATC frequencies"""
        def conv(r):
            orig, dest = {}, {}
            for ap in r or []:
                for f in ap.get("outboundFlights") or []:
                    orig[f] = ap["airportIcao"]
                for f in ap.get("inboundFlights") or []:
                    dest[f] = ap["airportIcao"]
            return {"orig": orig, "dest": dest}
        v, _, _ = self.world.get(s["id"], f"/sessions/{s['id']}/world", conv)
        return v or {"orig": {}, "dest": {}}

    def flight_list(self, key):
        """(server, converted list, fetch time, error)"""
        s, err = self.session(key)
        if not s:
            return None, [], 0, err or "no servers"
        raw, t, err = self.flights.get(s["id"], f"/sessions/{s['id']}/flights")
        if raw is None:
            return s, [], 0, err
        ck = (s["key"], t)
        if ck not in self.conv:
            for k in [k for k in self.conv if k[0] == s["key"]]:
                del self.conv[k]
            self.conv[ck] = self.convert(s, raw, t)
        return s, self.conv[ck], t, err

    def route_of(self, st, fid):
        o, d = st["orig"].get(fid), st["dest"].get(fid)
        if not o and not d:
            return None
        ao, ad = self.airports.by_id.get(o or ""), self.airports.by_id.get(d or "")
        return [o or "", ao[5] if ao else None, ao[6] if ao else None, d or "", ad[5] if ad else None, ad[6] if ad else None]

    def convert(self, s, raw, t):
        names, st = self.livery_names(), self.status(s)
        out = []
        for f in raw:
            lat, lon = f.get("latitude"), f.get("longitude")
            if lat is None or lon is None:
                continue
            gs, alt = f.get("speed") or 0, f.get("altitude") or 0
            ground = gs < 45 and abs(f.get("verticalSpeed") or 0) < 300
            ac, liv = names.get(f.get("liveryId"), ("", ""))
            out.append({"id": f["flightId"], "cs": (f.get("callsign") or "").strip() or "----", "lat": round(lat, 5), "lon": round(lon, 5),
                        "alt": int(alt), "gs": round(gs), "hdg": round(f.get("track") if f.get("track") is not None else f.get("heading") or 0, 1),
                        "vs": int(f.get("verticalSpeed") or 0), "ts": parse_t(f.get("lastReport")) or t, "ground": ground, "air": not ground,
                        "type": type_code(ac), "acName": ac, "livery": liv, "user": f.get("username") or "",
                        "vo": f.get("virtualOrganization") or "", "away": (f.get("pilotState") or 0) != 0,
                        "route": self.route_of(st, f["flightId"]), "reg": "", "sq": "", "emer": "", "hex": "", "cat": ""})
        return out

    def area(self, key, lat, lon, nm):
        s, acs, t, err = self.flight_list(key)
        if not self.c.configured:
            err = "no API key"
        dlat = nm / 60 + 0.1
        out = []
        for a in acs:
            if abs(a["lat"] - lat) > dlat:
                continue
            d = gc_nm(lat, lon, a["lat"], a["lon"])
            if d <= nm:
                out.append({**a, "dist": round(d, 1)})
        return {"ok": bool(t) and not err, "err": err, "t": t, "src": "Infinite Flight Live API", "srv": s and {k: s[k] for k in ("key", "name", "users")},
                "center": [round(lat, 3), round(lon, 3)], "nm": round(nm), "aircraft": out}

    def everywhere(self, key):
        s, acs, t, err = self.flight_list(key)
        ac = [[a["id"], a["lat"], a["lon"], round(a["hdg"]), a["gs"], round(a["alt"] / 100), int(a["ts"]), a["cs"], 1 if a["ground"] else 0]
              for a in acs]
        return {"ok": bool(t), "t": t, "every": 15, "src": "Infinite Flight", "ac": ac, "est": []}

    # ---------------------------------------------------------------- ATC, ATIS, one flight
    def atc_list(self, key):
        s, err = self.session(key)
        if not s:
            return {"ok": False, "err": err, "atc": []}

        def conv(r):
            return [{"icao": x.get("airportName") or "", "type": FREQ.get(x.get("type"), "ATC"), "user": x.get("username") or "",
                     "lat": x.get("latitude"), "lon": x.get("longitude"), "since": parse_t(x.get("startTime"))} for x in r or []]
        v, t, err = self.atc.get(s["id"], f"/sessions/{s['id']}/atc", conv)
        return {"ok": v is not None, "err": err, "t": t, "atc": v or []}

    def airport_atis(self, key, icao):
        s, _ = self.session(key)
        if not s or not re.fullmatch(r"[A-Z0-9]{3,4}", icao):
            return None
        v, _, err = self.atis.get((s["id"], icao), f"/sessions/{s['id']}/airport/{icao}/atis")
        return v if isinstance(v, str) else None

    def flight(self, key, fid):
        s, _ = self.session(key)
        if not s or not UUID.fullmatch(fid):
            return {"ok": False}

        def plan(r):
            pts = []

            def walk(items, proc):
                for it in items or []:
                    if it.get("children"):
                        walk(it["children"], it.get("name") or proc)
                        continue
                    loc = it.get("location") or {}
                    la, lo = loc.get("latitude"), loc.get("longitude")
                    if la is None or lo is None or (abs(la) < 1e-6 and abs(lo) < 1e-6):
                        continue
                    pts.append([it.get("name") or it.get("identifier") or "", round(la, 5), round(lo, 5), it.get("altitude", -1), proc or ""])
            walk((r or {}).get("flightPlanItems"), "")
            return {"ifr": (r or {}).get("flightPlanType") == 1, "pts": pts}
        p, _, perr = self.plans.get((s["id"], fid), f"/sessions/{s['id']}/flights/{fid}/flightplan", plan)
        out = {"ok": True, "plan": p, "planErr": perr}
        if s["key"] in ("expert", "training"):      # IF keeps flown routes only on these two
            r, _, rerr = self.routes.get((s["id"], fid), f"/sessions/{s['id']}/flights/{fid}/route",
                                         lambda r: [[round(x["latitude"], 4), round(x["longitude"], 4), round(x.get("altitude") or 0)] for x in r or []])
            out["track"], out["trackErr"] = r, rerr
        return out


class Metar(Atis):
    """the real METAR only (no FAA D-ATIS: the ATIS shown is Infinite Flight's)"""
    DATIS = False
    UA = {"User-Agent": "ifscope/1 (ifscope.kyleboas.com)"}


class Traffic:
    def __init__(self, live):
        self.live = live

    def get(self, lat, lon, nm, server=""):
        return self.live.area(server, lat, lon, nm)


class World:
    def __init__(self, live):
        self.live = live

    def get(self, server=""):
        body = json.dumps(self.live.everywhere(server), separators=(",", ":")).encode()
        return body, None


class IFAtis:
    def __init__(self, live):
        self.live, self.metar = live, Metar()

    def get(self, ident, server=""):
        d = self.metar.get(ident)
        txt = self.live.airport_atis(server, ident.upper())
        return {**d, "atis": [{"type": "if", "code": "", "text": txt, "time": ""}] if txt else []}


def endpoints(live):
    """/api/live/<name> handlers: each gets s(key, maxlen) for query strings"""
    def servers(s):
        v, err = live.servers()
        return {"ok": bool(v), "err": err if live.c.configured else "no API key", "servers": v}
    return {"servers": servers,
            "atc": lambda s: live.atc_list(s("srv", 10)),
            "flight": lambda s: live.flight(s("srv", 10), s("id", 40))}
