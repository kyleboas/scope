# scope

A watch-only, STARS-style scope of air traffic on a globe: the shared code behind several sites, one per
traffic source:

| site | traffic | address |
|---|---|---|
| `livescope` | real world, from public ADS-B feeds | https://livescope.kyleboas.com |
| `ifscope` | Infinite Flight (planned) | ifscope.kyleboas.com |

Every site shares the scope client, the server, airports, procedures and ground maps. A site is one
small file in `sites/` that names its data sources and links ([Adding a site](#adding-a-site)).

## livescope

The real-world site.

ADS-B positions come from adsb.lol, with adsb.fi as a fallback. The feed covers up to 250 nm around the
middle of the view, and positions are eased between reports. You can zoom out to an orthographic globe,
or search for any airport by ICAO, IATA or name. Close in, runways are drawn to scale.

### Features

- **Procedures:** US airports show their SIDs, STARs and approaches (FAA CIFP). Pick one in the airport
  card to highlight it with its fixes.
- **Airport card:** frequencies, the current ATIS (FAA D-ATIS through atis.info, US only) and the latest
  METAR (aviationweather.gov), plus a link to listen on LiveATC.net.
- **Ground maps:** zoomed in to an airport (GND / FLD), its taxiways, aprons, terminals and gates come
  from OpenStreetMap. The server fetches them once through Overpass, in the background, and caches them
  for 30 days in `livedata/ground/`. Taxiing aircraft leave history trails.
- **ALL / ARR / DEP / ARR+DEP** (bottom right) greys out and untags everything except the picked
  airport's arrivals and/or departures.
  - ADS-B has no flight plan, so these are guessed from track, altitude and climb/descent. Traffic goes
    to a nearby airport when it fits that one better.
  - Scheduled routes from adsbdb.com take precedence when the aircraft's position fits them.
- **ALT min–max** (header) greys out and untags traffic outside the band. It takes hundreds of feet,
  feet or FL350.
- **Worldwide traffic:** zoomed out past the 250 nm the live feeds cover, the globe shows every
  airborne aircraft as a dot, from OpenSky's `/states/all`.
  - Anonymously, that's one snapshot every 15 min. Set `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET`
    (a free OpenSky API client) to get one every 90 s.
  - No free feed covers the oceans, so airliners that leave every receiver's range at cruise are
    carried on toward their scheduled destination as estimates (hollow rings).
- **Split view:** the layout button (bottom left) cycles between one scope, big + small, and an even
  split. Each scope has its own view and layers; the second opens on the airport's field.
- **Measure:** right-drag or shift-drag (long-press then drag on touch) shows distance and bearing. If
  the line starts or ends on an aircraft, it also shows the time at that aircraft's ground speed.
- **Layers:** the stack button turns map layers on and off.
- **Views:** GND / FLD / APP / CTR / GLOBE set the zoom. The URL keeps the view (`#EGLL/40`,
  `#lat,lon,half-width-nm`).

## Run

```
python3 server.py livescope --port 8799     # Python 3.10+, standard library only; any site in sites/
```

Then open http://localhost:8799. `/` and `/live` serve the page; the API is under `/api/live`. Each site
runs as its own process (its own port and hostname), all from the same checkout.

## Adding a site

Write `sites/<name>.py` with two things:

- `SITE`, a dict:
  - required: `name` (also the localStorage prefix), `title` and `url`
  - optional: `port`; `old_hosts`, host prefixes to 301-redirect to `url`; `src_links`, feed name → URL
    for the status line; `hex_link`, `[url with {hex}, label with {HEX}]`; `world_link`, `[url, name]`
- `providers()`, which returns a dict:
  - `traffic` (required): an object whose `get(lat, lon, nm)` returns
    `{ok, t, center:[lat, lon], nm, src, aircraft:[...]}`. Each aircraft is
    `{id, cs, lat, lon, alt, gs, hdg, vs, ts, ground, air, type, reg, sq, emer}`, optionally with `hex`.
  - `max_nm` (required): the most the traffic source covers around a point.
  - `world` (optional): `get()` returns `(json_bytes, gzipped)` in OpenSky's compact form (see
    `sources/adsb.py` World).
  - `routes` (optional): `get([callsigns])` returns `{cs: [from, lat, lon, to, lat, lon]}` for the callsigns it knows.
  - `atis` (optional): `get(ident)` returns `{atis:[{type, code, text, time}], metar:{raw, cat} | None}`.

A provider left out turns its feature off in the page (no world dots, no ATIS block, no route lookups).
Put a site's data-source code in `sources/<source>.py`; anything every site can use belongs in `scope/`
or `web/scope.html`.

## Data

- `python3 -I tools/build_livescope.py <downloads>` (see the script) writes `livedata/airports.json` and
  `web/geo/lines.json` from OurAirports and Natural Earth.
- `python3 -I tools/build_procs.py FAACIFP18 livedata/procs.json` rebuilds the procedures. The FAA
  publishes a new CIFP every 28 days; the one included is cycle 2611.
- `web/geo/ksfo.json` holds KSFO's extended finals, from the atcscope project.

## Layout

```
server.py        HTTP server for one site: the page (with the site's settings), map files, /api/live*
sites/           one file per site: settings + which providers it uses
sources/adsb.py  livescope's data: ADS-B traffic, OpenSky world + ocean estimates, adsbdb routes, D-ATIS/METAR
scope/core.py    shared: geometry, airports (OurAirports), procedures (FAA CIFP), ground maps (OSM)
web/scope.html   the shared client (canvas, no build step)
web/geo/         coastlines/borders/states (Natural Earth) and KSFO finals
livedata/        airports (OurAirports), procedures (FAA CIFP); ground/ is a runtime cache
tools/           builders for livedata/ and web/geo/
```

Not for navigation. Licences and data sources: [NOTICE.md](NOTICE.md). The code is MIT ([LICENSE](LICENSE)).
