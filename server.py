"""livescope's web server: the page, its map files and the /api/live endpoints (live.py does the work).

    python3 server.py [--host 127.0.0.1] [--port 8798]

Optional environment: OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET (a free OpenSky API client) refresh the
worldwide picture every 90 s instead of every 15 min.
"""
import argparse
import gzip
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import live

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = {}            # path -> (body, gzipped)
OLD_HOSTS = ("liveatc.",)                  # the site's first name, redirected
CANONICAL = os.environ.get("LIVESCOPE_URL", "https://livescope.kyleboas.com")


def load_static():
    page = open(os.path.join(HERE, "web", "live.html"), "rb").read()
    files = {"/": (page, "text/html; charset=utf-8"), "/live": (page, "text/html; charset=utf-8")}
    for name in ("lines.json", "ksfo.json"):
        files["/live/" + name] = (open(os.path.join(HERE, "web", "geo", name), "rb").read(), "application/json")
    files["/live/major.json"] = (json.dumps(live.AIRPORTS.major, separators=(",", ":")).encode(), "application/json")
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
        if (self.headers.get("Host") or "").lower().startswith(OLD_HOSTS):
            self.send_response(301)
            self.send_header("Location", CANONICAL + self.path)
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
        if path == "/api/live":
            return self.send(200, live.TRAFFIC.get(f("lat"), f("lon"), max(5.0, min(live.MAX_NM, f("nm", 60)))))
        if path == "/api/live/area":
            return self.send(200, live.AIRPORTS.area(f("lat"), f("lon"), f("nm", 30)))
        if path == "/api/live/airport":
            return self.send(200, live.AIRPORTS.one(s("id")))
        if path == "/api/live/atis":
            return self.send(200, live.ATIS.get(s("id")))
        if path == "/api/live/ground":
            gz, state = live.GROUND.get(s("id"))
            if gz is None:
                return self.send(200, {"state": state})
            return self.send(200, gzip.decompress(gz), gz=gz)
        if path == "/api/live/world":
            body, gz = live.WORLD.get()
            return self.send(200, body, gz=gz)
        if path == "/api/live/routes":
            return self.send(200, live.ROUTES.get(s("cs", 2000).split(",")[:80]))
        if path == "/api/live/procs":
            return self.send(200, live.PROCS.area(f("lat"), f("lon"), f("nm", 30), s("id")))
        if path == "/api/live/search":
            return self.send(200, live.AIRPORTS.search(s("q", 40)))
        self.send(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8798)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    load_static()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"livescope: http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
