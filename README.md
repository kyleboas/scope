# scope

A watch-only, STARS-style scope of air traffic that zooms out to a globe: the shared server and client
behind several sites. Each site is its own repo that plugs in one traffic source:

| site | traffic | address |
|---|---|---|
| [livescope](https://github.com/kyleboas/livescope) | real world, from public ADS-B feeds | https://livescope.kyleboas.com |
| [infinitescope](https://github.com/kyleboas/infinitescope) | Infinite Flight's live multiplayer servers | https://infinitescope.kyleboas.com |

scope gives every site the page (canvas, no build step), airports and runways, ILS and extended finals worldwide, US procedures (narrowed to the ones in use, read from the ATIS), FAA airport
diagrams laid on the map and the rest of the FAA's charts (SIDs, STARs, approaches, minimums; US), OSM ground maps, a street map or satellite background (MAP), ATIS/METAR, split view, measuring, layers, ARR/DEP and altitude filters. See
[livescope's README](https://github.com/kyleboas/livescope#readme) for the full feature list.

## Run

Check scope out next to a site and point the server at the site's directory:

```
git clone https://github.com/kyleboas/scope
git clone https://github.com/kyleboas/livescope
python3 scope/server.py livescope --port 8799     # Python 3.10+, standard library only
```

Then open http://localhost:8799. `/` and `/live` serve the page; the API is under `/api/live`. Each site
runs as its own process (its own port and hostname); they can all share one scope checkout.

Environment: `SCOPE_GROUND_DIR` moves the ground-map cache (default `livedata/ground/` in this checkout),
for example when the server runs as a user that can't write here. The FAA airport diagram cache goes in its `diagrams/`
(or `SCOPE_DIAGRAM_DIR`; default `livedata/diagrams/`).

## Writing a site

A site is a directory (normally its own repo) with `site.py`. The server puts scope and the site's
directory on `sys.path`, so `site.py` can `import` the site's other modules and anything in `scope`
(`scope.core` geometry, `scope.weather.Atis`). `site.py` holds two things:

- `SITE`, a dict:
  - required: `name` (also the localStorage prefix), `title` and `url`
  - optional: `port`; `old_hosts`, host prefixes to 301-redirect to `url`; `src_links`, feed name → URL
    for the status line; `hex_link`, `[url with {hex}, label with {HEX}]`; `world_link`, `[url, name]`;
    `no_history` (no trails); `hist_s` (seconds of trail the page keeps, default 32); `stale_s` (how long to dead-reckon a report, default 20); `idle_min` (stop
    polling while hidden or after that many minutes without input); `poll_ms`, `world_ms` (page refresh,
    defaults 2000 and 30000); `start` (hash to open on, default `KSFO/52`; `None` = the globe);
    `metar_label`; `audio`, ICAO → `[[label, stream URL], ...]`, live audio buttons in the airport card
    (MP3 streams are fed through Media Source Extensions when the server sends CORS headers, so they start
    in a second or two instead of 10–15 s; anything else plays in a plain `<audio>`)
- `providers()` (or `providers(airports=None)` to get the shared `core.Airports`), which returns a dict:
  - `traffic` (required): an object whose `get(lat, lon, nm)` returns
    `{ok, t, center:[lat, lon], nm, src, aircraft:[...]}`. Each aircraft is
    `{id, cs, lat, lon, alt, gs, hdg, vs, ts, ground, air, type, reg, sq, emer}`, optionally with `hex`.
  - `max_nm` (required): the most the traffic source covers around a point.
  - `world` (optional): `get()` returns `(json_bytes, gzipped)` in OpenSky's compact form (see
    livescope's `adsb.py` World).
  - `routes` (optional): `get([callsigns])` returns `{cs: [from, lat, lon, to, lat, lon]}` for the callsigns it knows.
  - `atis` (optional): `get(ident)` returns `{atis:[{type, code, text, time}], metar:{raw, cat} | None}`.
  - `features` (optional): extra page features: `aircraft` (the aircraft card shows everything about the selected
    aircraft from an `aircraft` endpoint: `?hex=` returns `{ok, hex, t, src, ac: the feed's readsb record, db:{desc, ownOp,
    year}, country:[name, ISO], typeinfo:{desc, engines, kind, wake}, photo:{src, link, by}}`; `scope.aircraft.Lookup` gives
    the country and type), `servers` (a server picker; then `traffic`, `world` and
    `atis` get a `server=` keyword, from the page's `srv`), `atc`, `flight` and `timelapse` (a header
    button and a playback bar for recordings served by a `timelapse` endpoint; see livescope's `timelapse.py`),
    `wx` (an Airspace and weather group in Layers, all off by default: TFRs, SIGMETs, G-AIRMETs, CWAs and PIREPs from a `wx`
    endpoint that returns the whole world, `{ok, t, areas:[{k, id, name, hz, alt, from, to, text, poly:[[[lat, lon], ...]]}],
    pireps:[[lat, lon, FL or -1, kind 0 AIREP / 1 PIREP / 2 urgent, ts, raw, turbulence, icing]]}`, k one of tfr, sigmet,
    csigmet, isigmet, airmet, cwa; clicking inside an area or on a report shows its text; see livescope's `hazards.py`),
    `history` (a Flights list in the aircraft card, each replayed on the scope with the timelapse bar, `?fh=<hex>&t=<start>`,
    from a `history` endpoint: `?hex=` returns `{ok, every_s, keep_h, flights:[{t0, t1, cs, from, to, top, gnd, live,
    pts:[[t, lat, lon, alt ft, gs, track, k: 0 air / 1 ground / 2 estimated]]}]}`; `?a=around&hex=&t0=&t1=&nm=` returns
    `{ok, every_s, frames:[[t, OpenSky compact rows, estimate rows]]}`, the other aircraft within nm of it, for the replay's
    TRAFFIC; the replay also charts altitude and ground speed (PROFILE); see livescope's `history.py`) and
    `boats` (a Boats layer, off by default, from a `boats` endpoint: `?lat=&lon=&nm=` returns `{ok, t, src, v:[[mmsi, lat,
    lon, sog kt, cog, heading or -1, ts, name, AIS ship type, destination, nav status]]}`; see livescope's `boats.py`).
  - `endpoints` (optional): `{name: fn(s)}` for `/api/live/<name>`, where `s(key, maxlen)` reads the
    query string. infinitescope's: `servers`, `atc` (`{ok, atc:[{icao, type, user, lat, lon, since}]}`) and
    `flight` (`{plan:{ifr, pts:[[name, lat, lon, alt, proc]]}, track:[[lat, lon, alt]]}`).
  - An aircraft may carry `route` (`[from, lat, lon, to, lat, lon]`): it is trusted over `routes`.

A provider left out turns its feature off in the page (no world dots, no ATIS block, no route lookups).
Anything every site can use belongs in scope (`scope/` or `web/scope.html`), not in a site.

## Data

- `python3 -I tools/build_airports.py <downloads>` (see the script) writes `livedata/airports.json` and
  `web/geo/lines.json` from OurAirports and Natural Earth.
- `python3 -I tools/build_procs.py FAACIFP18 livedata/procs.json` rebuilds the procedures. The FAA
  publishes a new CIFP every 28 days; the one included is cycle 2611.
- `python3 -I tools/build_ils.py nav.dat.gz` writes `livedata/ils.json`, the world's ILS and localizers (Robin Peel's
  navaids, GPL, cycle 2013.10; see the script for the download), matched to the runways in `livedata/airports.json`.
  The page draws a 10 nm final along each localizer, and along the runway itself on long runways that have none on file.
- `web/geo/ksfo.json` holds KSFO's extended finals, from the atcscope project.
- FAA airport diagrams aren't stored: `/api/live/diagram?id=` fetches the current d-TPP cycle's PDF from aeronav.faa.gov (the
  cycle's index is read once a cycle) and caches it. The page draws it with pdf.js (from jsDelivr, loaded only when a diagram
  is wanted) and places it from the chart itself: its runway bars matched to the runways on file, then its latitude and
  longitude lines snapped to their half minutes. A diagram it can't place (about one in ten) isn't drawn. The overlay is off
  until turned on ('Diagram on map' in the airport card, or the layer).
- `/api/live/charts?id=` lists the airport's charts in the current cycle (from the same index); the card links each PDF on
  aeronav.faa.gov. Only the diagram goes on the map: SID and STAR charts aren't to scale.

## Layout

```
server.py        HTTP server for one site: the page (with the site's settings), map files, /api/live*
scope/core.py    geometry, airports (OurAirports) and their ILS, procedures (FAA CIFP), ground maps (OSM), FAA airport diagrams
scope/weather.py D-ATIS (atis.info) and METARs (aviationweather.gov)
web/scope.html   the shared client (canvas, no build step)
web/geo/         coastlines/borders/states (Natural Earth) and KSFO finals
livedata/        airports (OurAirports), procedures (FAA CIFP); ground/ and timelapse/ are written at runtime
tools/           builders for livedata/ and web/geo/
```

Not for navigation. Licences and data sources: [NOTICE.md](NOTICE.md). The code is MIT ([LICENSE](LICENSE)).
