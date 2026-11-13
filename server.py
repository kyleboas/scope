"""scope's web server: the page, its map files and the /api/live endpoints for one site.

    python3 server.py ../livescope [--host 127.0.0.1] [--port 8799]

A site is its own repo (a directory with site.py) that gives its name, links and data providers;
everything else is shared (scope/, web/scope.html). Site code can import its own modules and scope's.
"""
import argparse
import gzip
import html
import importlib.util
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from scope import core

HERE = os.path.dirname(os.path.abspath(__file__))
SITE, P, STATIC = {}, {}, {}          # the site's settings, its providers, path -> (body, gzipped, type)
AIRPORTS = PROCS = GROUND = None


def load(site_dir):
    global AIRPORTS, PROCS, GROUND
    site_dir = os.path.abspath(site_dir)
    path = os.path.join(site_dir, "site.py")
    if not os.path.isfile(path):
        raise SystemExit(f"no site.py in {site_dir}")
    sys.path[:0] = [HERE, site_dir]             # scope's package, then the site's own modules
    spec = importlib.util.spec_from_file_location("scope_site", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    SITE.update(mod.SITE)
    AIRPORTS = core.Airports()
    P.update(mod.providers(airports=AIRPORTS) if "airports" in mod.providers.__code__.co_varnames else mod.providers())
    PROCS = core.Procs(AIRPORTS)
    GROUND = core.Ground(AIRPORTS)
    feats = ["procs", "ground"] + [k for k in ("world", "routes", "atis") if P.get(k)] + list(P.get("features", []))
    client = {k: v for k, v in SITE.items() if k not in ("old_hosts", "port")} | {"features": feats}
    page = open(os.path.join(HERE, "web", "scope.html"), encoding="utf-8").read()
    page = page.replace("<title>livescope</title>", f"<title>{html.escape(SITE['title'])}</title>", 1)
    page = page.replace("<script>\n", "<script>\nconst SITE = " + json.dumps(client).replace("</", "<\\/") + ";\n", 1).encode()
    files = {"/": (page, "text/html; charset=utf-8"), "/live": (page, "text/html; charset=utf-8")}
    for f in ("lines.json", "ksfo.json"):
        files["/live/" + f] = (open(os.path.join(HERE, "web", "geo", f), "rb").read(), "application/json")
    files["/live/major.json"] = (json.dumps(AIRPORTS.major, separators=(",", ":")).encode(), "application/json")
    for path, (body, ctype) in files.items():
        STATIC[path] = (body, gzip.compress(body, 9), ctype)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json", gz=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, separators=(",", ":")).encode()
        elif isinstance(body, str):
            body = body.encode()
        zipped = "gzip" in (self.headers.get("Accept-Encoding") or "") and len(body) > 2048
        if zipped:
            body = gz or gzip.compress(body, 5)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if zipped:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            self.get()
        except (ValueError, KeyError):
            self.send(400, {"error": "bad request"})

    def get(self):
        path, _, qs = self.path.partition("?")
        if SITE.get("old_hosts") and (self.headers.get("Host") or "").lower().startswith(tuple(SITE["old_hosts"])):
            self.send_response(301)
            self.send_header("Location", SITE["url"] + self.path)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/index.html":
            path = "/"
        if path in STATIC:
            body, gz, ctype = STATIC[path]
            return self.send(200, body, ctype, gz=gz)
        q = parse_qs(qs)
        f = lambda k, d=0.0: float((q.get(k) or [d])[0])       # noqa: E731
        s = lambda k, n=12: (q.get(k) or [""])[0][:n]          # noqa: E731
        kw = {"server": s("srv", 10)} if "servers" in P.get("features", []) else {}   # sites with several servers (infinitescope)
        if path == "/api/live":
            return self.send(200, P["traffic"].get(f("lat"), f("lon"), max(5.0, min(P["max_nm"], f("nm", 60))), **kw))
        if path == "/api/live/area":
            return self.send(200, AIRPORTS.area(f("lat"), f("lon"), f("nm", 30)))
        if path == "/api/live/airport":
            return self.send(200, AIRPORTS.one(s("id")))
        if path == "/api/live/search":
            return self.send(200, AIRPORTS.search(s("q", 40)))
        if path == "/api/live/procs":
            return self.send(200, PROCS.area(f("lat"), f("lon"), f("nm", 30), s("id")))
        if path == "/api/live/ground":
            gz, state = GROUND.get(s("id"))
            if gz is None:
                return self.send(200, {"state": state})
            return self.send(200, gzip.decompress(gz), gz=gz)
        if path == "/api/live/atis" and P.get("atis"):
            return self.send(200, P["atis"].get(s("id"), **kw))
        if path == "/api/live/world" and P.get("world"):
            body, gz = P["world"].get(**kw)
            return self.send(200, body, gz=gz)
        if path == "/api/live/routes" and P.get("routes"):
            return self.send(200, P["routes"].get(s("cs", 2000).split(",")[:80]))
        name = path[len("/api/live/"):] if path.startswith("/api/live/") else ""
        if name in P.get("endpoints", {}):                 # a site's own endpoints (infinitescope: servers, atc, flight)
            return self.send(200, P["endpoints"][name](s))
        self.send(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site", help="the site's directory (its repo checkout, with site.py)")
    ap.add_argument("--port", type=int)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    load(args.site)
    port = args.port or SITE.get("port", 8799)
    srv = ThreadingHTTPServer((args.host, port), Handler)
    print(f"{SITE['name']}: http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
