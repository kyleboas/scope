"""livescope (https://livescope.kyleboas.com): real-world traffic from public ADS-B feeds."""
from sources import adsb

SITE = {
    "name": "livescope",
    "title": "livescope",
    "url": "https://livescope.kyleboas.com",
    "old_hosts": ["liveatc."],            # the site's first name, 301-redirected here
    "port": 8799,
    "about": "real ADS-B traffic anywhere, on a STARS-style scope that zooms out to the globe",
    # links shown in the page: the feed by name, and an aircraft's page by its ICAO hex
    "src_links": {"adsb.lol": "https://adsb.lol", "adsb.fi": "https://adsb.fi"},
    "hex_link": ["https://adsb.lol/?icao={hex}", "{HEX} on adsb.lol"],
    "world_link": ["https://opensky-network.org", "OpenSky"],
}


def providers():
    """The site's data: traffic is required; world, routes and atis are optional (left out = feature off)."""
    routes = adsb.Routes()
    return {"traffic": adsb.Traffic(), "world": adsb.World(routes), "routes": routes, "atis": adsb.Atis(),
            "max_nm": adsb.MAX_NM}
