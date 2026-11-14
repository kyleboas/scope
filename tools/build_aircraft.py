"""Build livedata/aircraft.json: what an aircraft's ICAO type code and 24-bit address say about it (run again to refresh).

    python3 -I tools/build_aircraft.py flags.js icao_aircraft_types2.js [livedata/aircraft.json]

flags.js is tar1090's table of ICAO address blocks by country (from ICAO Annex 10 Vol III, Chapter 9):
  https://raw.githubusercontent.com/wiedehopf/tar1090/master/html/flags.js
icao_aircraft_types2.js is tar1090-db's ICAO type designators (ICAO Doc 8643), gzipped JSON:
  https://raw.githubusercontent.com/wiedehopf/tar1090-db/master/db/icao_aircraft_types2.js

Writes {"ranges": [[first, last, country, ISO code]], "types": {type: [description, class (L2J ...), wake (L/M/H/J)]}}.
"""
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    flags, types = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "livedata", "aircraft.json")
    src = open(flags, encoding="utf-8").read()
    ranges = [[int(a, 16), int(b, 16), c, (cc or "").upper()] for a, b, c, cc in re.findall(
        r'start:\s*0x([0-9A-Fa-f]+),\s*end:\s*0x([0-9A-Fa-f]+),\s*country:\s*"([^"]+)",\s*country_code:\s*(?:"([a-z]*)"|null)', src)]
    ranges.sort()
    raw = open(types, "rb").read()
    t = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    t = {k: [v[0] or "", v[1] or "", v[2] or ""] for k, v in sorted(t.items()) if isinstance(v, list) and len(v) >= 3}
    if len(ranges) < 150 or len(t) < 1000:
        raise SystemExit(f"only {len(ranges)} ranges and {len(t)} types: has the source changed?")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"ranges": ranges, "types": t}, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{out}: {len(ranges)} address blocks, {len(t)} types")


if __name__ == "__main__":
    main()
