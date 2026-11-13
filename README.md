# scope

A watch-only, STARS-style scope of air traffic on a globe: the shared code behind several sites, one per
traffic source:

| site | traffic | address |
|---|---|---|
| `livescope` | real world, from public ADS-B feeds | https://livescope.kyleboas.com |
| `ifscope` | Infinite Flight's live multiplayer servers | https://ifscope.kyleboas.com |

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

## ifscope

The Infinite Flight site: the Casual, Training and Expert servers' flights and controllers, from the
[Infinite Flight Live API](https://infiniteflight.com/guide/developer-reference). It needs credentials in
the environment, server side only:

- `IF_API_KEY`: a Live API v2 key (Infinite Flight no longer issues these), or
- `IF_CLIENT_ID` / `IF_CLIENT_SECRET`: a PublicApi v3 *Confidential* client with *Allow server-to-server
  access*, created at https://infiniteflight.com/account/api-keys and approved by Infinite Flight.
- `IF_RPM` (optional): requests per minute to allow, 25 by default. The limit is 30, or 100 when the
  account that owns the key has Pro.

Everything above works the same, plus:

- **Servers** (header): Casual / Training / Expert with their pilot counts.
- **All flights:** each server's whole flight list comes in one request, so the globe shows every
  flight, refreshed every 15 s.
- **ATC on duty:** airports with controllers get a cyan box and their facilities (C G T A D). The
  airport card lists the controllers, any Center within 400 nm, the in-game ATIS and the real METAR.
- **Flight plans:** each aircraft's origin and destination come from its filed plan, so ARR / DEP use
  that first. Selecting an aircraft shows its pilot, livery and full plan (dashed). On Expert and
  Training it also shows the route it has flown (blue), from Infinite Flight.
- **Infinite Flight's API rules** ([usage and data rules](https://infiniteflight.com/guide/developer-reference/api-rules/usage-and-data-rules))
  are built in (`sources/infinite_flight.py`):
  - one shared in-memory cache, never written to disk or logged, and dropped after 50 minutes;
  - minimum intervals: flights 15 s, ATC and world status 60 s, sessions 10 min, aircraft/liveries
    60 min; a flight's plan or route only when someone selects it;
  - a 429 pauses all requests for its `Retry-After`;
  - no history trails, which would be collected positions;
  - the page stops polling while hidden and after 15 minutes without input.

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
    for the status line; `hex_link`, `[url with {hex}, label with {HEX}]`; `world_link`, `[url, name]`;
    `no_history` (no trails); `stale_s` (how long to dead-reckon a report, default 20); `idle_min` (stop
    polling while hidden or after that many minutes without input); `poll_ms`, `world_ms` (page refresh,
    defaults 2000 and 30000); `start` (hash to open on, default `KSFO/52`; `None` = the globe);
    `metar_label`
- `providers()` (or `providers(airports=None)` to get the shared `core.Airports`), which returns a dict:
  - `traffic` (required): an object whose `get(lat, lon, nm)` returns
    `{ok, t, center:[lat, lon], nm, src, aircraft:[...]}`. Each aircraft is
    `{id, cs, lat, lon, alt, gs, hdg, vs, ts, ground, air, type, reg, sq, emer}`, optionally with `hex`.
  - `max_nm` (required): the most the traffic source covers around a point.
  - `world` (optional): `get()` returns `(json_bytes, gzipped)` in OpenSky's compact form (see
    `sources/adsb.py` World).
  - `routes` (optional): `get([callsigns])` returns `{cs: [from, lat, lon, to, lat, lon]}` for the callsigns it knows.
  - `atis` (optional): `get(ident)` returns `{atis:[{type, code, text, time}], metar:{raw, cat} | None}`.
  - `features` (optional): extra page features: `servers` (a server picker; then `traffic`, `world` and
    `atis` get a `server=` keyword, from the page's `srv`), `atc` and `flight`.
  - `endpoints` (optional): `{name: fn(s)}` for `/api/live/<name>`, where `s(key, maxlen)` reads the
    query string. ifscope's: `servers`, `atc` (`{ok, atc:[{icao, type, user, lat, lon, since}]}`) and
    `flight` (`{plan:{ifr, pts:[[name, lat, lon, alt, proc]]}, track:[[lat, lon, alt]]}`).
  - An aircraft may carry `route` (`[from, lat, lon, to, lat, lon]`): it is trusted over `routes`.

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
sources/infinite_flight.py  ifscope's data: Infinite Flight Live API (flights, ATC, ATIS, flight plans)
scope/core.py    shared: geometry, airports (OurAirports), procedures (FAA CIFP), ground maps (OSM)
web/scope.html   the shared client (canvas, no build step)
web/geo/         coastlines/borders/states (Natural Earth) and KSFO finals
livedata/        airports (OurAirports), procedures (FAA CIFP); ground/ is a runtime cache
tools/           builders for livedata/ and web/geo/
```

Not for navigation. Licences and data sources: [NOTICE.md](NOTICE.md). The code is MIT ([LICENSE](LICENSE)).
