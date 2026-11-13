# Notices

scope's code (livescope, ifscope) is MIT-licensed (see LICENSE). The data it ships with or fetches is not all under that licence:

- **Airports, runways and frequencies** are from OurAirports (public domain, <https://ourairports.com/data/>).
- **Coastlines, borders and state/province lines** are from Natural Earth (public domain, <https://www.naturalearthdata.com>).
- **US SIDs, STARs and approaches** are from FAA CIFP (U.S. Government work, public domain; cycle 2611). Not for navigation.
- **Ground maps** (taxiways, aprons, terminals, gates, holding positions) are © OpenStreetMap contributors and available under
  the Open Database License (ODbL) 1.0: <https://www.openstreetmap.org/copyright>. They are fetched at run time through the
  Overpass API and cached in `livedata/ground/`; that cache is under the ODbL.
- **Live positions** are fetched at run time from adsb.lol (ODbL) or adsb.fi and are not stored.
- **The worldwide picture** is from The OpenSky Network (<https://opensky-network.org>, non-commercial use).
- **Scheduled routes** are from adsbdb.com; **ATIS** from atis.info (FAA D-ATIS); **METARs** from aviationweather.gov.
- **Infinite Flight data** (ifscope: flights, controllers, ATIS, flight plans and routes) comes from the Infinite Flight Live
  API and belongs to Infinite Flight. It is fetched at run time, kept only in memory under Infinite Flight's API usage
  rules, and not stored. Not affiliated with Infinite Flight.
- **Icons** are from Tabler Icons (MIT).
