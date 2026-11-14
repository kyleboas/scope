"""What an aircraft's ICAO type code and 24-bit address say about it, for any site with real ADS-B traffic:
the type's name, class and wake category (ICAO Doc 8643) and the country the address was issued to (ICAO
Annex 10). From livedata/aircraft.json, built by tools/build_aircraft.py."""
import bisect
import json
import os

from scope.core import HERE

ENGINES = {"J": "jet", "T": "turboprop", "P": "piston", "E": "electric", "R": "rocket"}
KINDS = {"L": "landplane", "S": "seaplane", "A": "amphibian", "H": "helicopter", "G": "gyrocopter", "T": "tiltrotor"}
WAKE = {"L": "light", "M": "medium", "H": "heavy", "J": "super"}


class Lookup:
    def __init__(self):
        path = os.path.join(HERE, "livedata", "aircraft.json")
        d = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"ranges": [], "types": {}}
        self.ranges, self.types = d["ranges"], d["types"]
        self.starts = [r[0] for r in self.ranges]

    def country(self, hexid):
        """(country, ISO code) the address block belongs to, or None"""
        try:
            n = int(hexid, 16)
        except (TypeError, ValueError):
            return None
        i = bisect.bisect_right(self.starts, n) - 1
        return (self.ranges[i][2], self.ranges[i][3]) if i >= 0 and n <= self.ranges[i][1] else None

    def type(self, code):
        """{desc, engines ("2 jet"), kind, wake} for an ICAO type designator, or None"""
        t = self.types.get((code or "").upper())
        if not t:
            return None
        desc, cls, wake = t
        out = {"desc": desc, "wake": WAKE.get(wake, "")}
        if len(cls) == 3:
            n = {"C": "coupled"}.get(cls[1], cls[1])
            out["kind"] = KINDS.get(cls[0], "")
            eng = "turboshaft" if cls[2] == "T" and cls[0] in "HGT" else ENGINES.get(cls[2], "")
            out["engines"] = f"{n} {eng}".strip() if cls[1] != "0" else ""
        return out
