# Notices

scope's code is MIT-licensed (see LICENSE). The data it ships with or fetches is not all under that licence (each site's own
feeds are in that site's NOTICE):

- **Airports, runways and frequencies** are from OurAirports (public domain, <https://ourairports.com/data/>).
- **Coastlines, borders and state/province lines** are from Natural Earth (public domain, <https://www.naturalearthdata.com>).
- **US SIDs, STARs and approaches** are from FAA CIFP (U.S. Government work, public domain; cycle 2611). Not for navigation.
- **ILS and localizers** (`livedata/ils.json`) are from Robin A. Peel's navaid database (data cycle 2013.10, as shipped by
  FlightGear), © 2013 Robin A. Peel, under the GNU General Public License v2 or later:
  <https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>. `tools/build_ils.py` rebuilds the file from that source. The data
  is from 2013, so newer ILS are missing and some may have changed. Not for navigation.
- **Ground maps** (taxiways, aprons, terminals, gates, holding positions) are © OpenStreetMap contributors and available under
  the Open Database License (ODbL) 1.0: <https://www.openstreetmap.org/copyright>. They are fetched at run time through the
  Overpass API and cached in `livedata/ground/`; that cache is under the ODbL.
- **Aircraft types and address countries** (`livedata/aircraft.json`, from `tools/build_aircraft.py`): ICAO type designators
  (ICAO Doc 8643) as compiled by tar1090-db (<https://github.com/wiedehopf/tar1090-db>), and the ICAO 24-bit address blocks by
  country (ICAO Annex 10 Vol III) as listed by tar1090 (<https://github.com/wiedehopf/tar1090>).
- **Airport diagrams** are the FAA's (d-TPP, U.S. Government work, public domain), fetched at run time from aeronav.faa.gov
  and cached for the cycle. Not for navigation. They're drawn in the page with **pdf.js** (Mozilla, Apache License 2.0,
  <https://github.com/mozilla/pdf.js>), loaded from jsDelivr.
- **ATIS** is from atis.info (FAA D-ATIS); **METARs**, and the weather layers' **SIGMETs, G-AIRMETs, CWAs and PIREPs**,
  from aviationweather.gov (NOAA/NWS Aviation Weather Center; US government data, not for navigation).
- **Map backgrounds** (the MAP button: street map and satellite) are Esri's tile services, loaded by the browser at run time:
  the Dark Gray Canvas (Esri, HERE, Garmin, © OpenStreetMap contributors) and World Imagery (Esri, Maxar, Earthstar Geographics).
  They are credited on the map while shown.
- **Weather radar** (Layers: Radar) is RainViewer's (<https://www.rainviewer.com/api.html>) zoomed out, and close in near a
  NEXRAD the nearest site's own scan (NOAA/NWS, US government data) through the Iowa Environmental Mesonet
  (<https://mesonet.agron.iastate.edu>); both loaded by the browser at run time and credited on the map while shown.
- **Icons** are from Tabler Icons (MIT).
