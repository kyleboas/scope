"""Build livescope's map data from public-domain sources (run again to refresh).

    python3 -I tools/build_livescope.py SRC_DIR

SRC_DIR holds the downloads:
  OurAirports (public domain)  https://davidmegginson.github.io/ourairports-data/{airports,runways,airport-frequencies}.csv
  Natural Earth (public domain) https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
      ne_50m_coastline, ne_50m_admin_0_boundary_lines_land, ne_50m_admin_1_states_provinces_lines (.geojson)
Writes livedata/airports.json (server) and web/geo/lines.json (client).
"""
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIND = {"large_airport": "L", "medium_airport": "M", "small_airport": "S", "seaplane_base": "W"}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def dest(lat, lon, brg, nm):
    d, b, p1, l1 = nm / 3440.065, math.radians(brg), math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def airports(src):
    out, by_ref = [], {}
    for r in csv.DictReader(open(os.path.join(src, "airports.csv"), encoding="utf-8")):
        k = KIND.get(r["type"])
        lat, lon = num(r["latitude_deg"]), num(r["longitude_deg"])
        if not k or lat is None or lon is None:
            continue
        a = [r["icao_code"] or r["gps_code"] or r["ident"], r["iata_code"], r["name"], r["municipality"], r["iso_country"],
             round(lat, 5), round(lon, 5), int(num(r["elevation_ft"]) or 0), k, [], []]
        out.append(a)
        by_ref[r["id"]] = a
    for r in csv.DictReader(open(os.path.join(src, "runways.csv"), encoding="utf-8")):
        a = by_ref.get(r["airport_ref"])
        if a is None or r["closed"] == "1":
            continue
        la1, lo1, la2, lo2 = (num(r[f]) for f in ("le_latitude_deg", "le_longitude_deg", "he_latitude_deg", "he_longitude_deg"))
        if None in (la1, lo1, la2, lo2):          # no ends: from the airport point, the heading and the length
            hdg, ln = num(r["le_heading_degT"]), num(r["length_ft"])
            if hdg is None or not ln or a[8] == "W":
                continue
            half = ln / 6076.12 / 2
            la1, lo1 = dest(a[5], a[6], hdg + 180, half)
            la2, lo2 = dest(a[5], a[6], hdg, half)
        a[9].append([r["le_ident"], r["he_ident"], round(la1, 5), round(lo1, 5), round(la2, 5), round(lo2, 5), int(num(r["width_ft"]) or 100)])
    for r in csv.DictReader(open(os.path.join(src, "airport-frequencies.csv"), encoding="utf-8")):
        a, mhz = by_ref.get(r["airport_ref"]), num(r["frequency_mhz"])
        if a is not None and mhz:
            a[10].append([r["type"], r["description"], round(mhz, 3)])
    return out


def lines(src, name, nd=2):
    d = json.load(open(os.path.join(src, name + ".geojson"), encoding="utf-8"))
    out = []
    for f in d["features"]:
        g = f["geometry"]
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for p in parts:
            flat = []
            for lon, lat in p:
                flat += [round(lon, nd), round(lat, nd)]
            if len(flat) >= 4:
                out.append(flat)
    return out


def main():
    src = sys.argv[1]
    os.makedirs(os.path.join(HERE, "livedata"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "web", "geo"), exist_ok=True)
    ap = airports(src)
    with open(os.path.join(HERE, "livedata", "airports.json"), "w") as f:
        json.dump(ap, f, separators=(",", ":"), ensure_ascii=False)
    geo = {"coast": lines(src, "ne_50m_coastline"), "borders": lines(src, "ne_50m_admin_0_boundary_lines_land"),
           "states": lines(src, "ne_50m_admin_1_states_provinces_lines")}
    with open(os.path.join(HERE, "web", "geo", "lines.json"), "w") as f:
        json.dump(geo, f, separators=(",", ":"))
    print(len(ap), "airports,", sum(len(a[9]) for a in ap), "runways")


if __name__ == "__main__":
    main()
