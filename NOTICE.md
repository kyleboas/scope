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
- **ATIS** is from atis.info (FAA D-ATIS); **METARs** from aviationweather.gov.
- **Icons** are from Tabler Icons (MIT).
