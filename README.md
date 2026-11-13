# livescope

A watch-only, STARS-style scope of real air traffic anywhere in the world. It runs live at
https://livescope.kyleboas.com.

ADS-B positions come from adsb.lol, with adsb.fi as a fallback. The feed covers up to 250 nm around the
middle of the view, and positions are eased between reports. You can zoom out to an orthographic globe,
or search for any airport by ICAO, IATA or name. Close in, runways are drawn to scale.

## Features

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
python3 server.py --port 8798        # Python 3.10+, standard library only
```

Then open http://localhost:8798. `/` and `/live` serve the page; the API is under `/api/live`.

## Data

- `python3 -I tools/build_livescope.py <downloads>` (see the script) writes `livedata/airports.json` and
  `web/geo/lines.json` from OurAirports and Natural Earth.
- `python3 -I tools/build_procs.py FAACIFP18 livedata/procs.json` rebuilds the procedures. The FAA
  publishes a new CIFP every 28 days; the one included is cycle 2611.
- `web/geo/ksfo.json` holds KSFO's extended finals, from the atcscope project.

## Layout

```
server.py        HTTP server: the page, its map files, /api/live*
live.py          traffic cache, airports, procedures, routes, OpenSky world + estimates, ground maps, ATIS
web/live.html    the whole client (canvas, no build step)
web/geo/         coastlines/borders/states (Natural Earth) and KSFO finals
livedata/        airports (OurAirports), procedures (FAA CIFP); ground/ is a runtime cache
tools/           builders for livedata/ and web/geo/
```

Not for navigation. Licences and data sources: [NOTICE.md](NOTICE.md). The code is MIT ([LICENSE](LICENSE)).
