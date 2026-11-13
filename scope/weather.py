"""Real-world weather any site can use: the FAA's D-ATIS (through atis.info) and aviationweather.gov METARs."""
import json
import re
import threading
import time
import urllib.error
import urllib.request


class Atis:
    """Current ATIS for an airport: the FAA's D-ATIS text through atis.info (US airports that have it),
    plus the latest METAR from aviationweather.gov for any airport. Fetched when asked, kept a few minutes."""
    UA = {"User-Agent": "scope/1 (+https://github.com/kyleboas/scope)"}
    DATIS = True               # False: the METAR only

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
                if self.DATIS and ident[0] in "KPT" and len(ident) == 4:
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
