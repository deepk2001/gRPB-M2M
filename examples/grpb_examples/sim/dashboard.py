"""FarmNet dashboard: an ordinary oneM2M HTTP/JSON client, unaware of Protobuf.

It finds every FarmNet sensor in the CSE (AEs labelled app:farmnet) and shows each one's latest
reading, fetched over HTTP as JSON. The sensors write in Protobuf over MQTT; nothing here changes.

    python -m grpb_examples.sim dashboard --port 8090        # then open http://<pi>:8090
"""

from __future__ import annotations

import argparse
import html
import json
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from grpb.config import Config


def get(cfg: Config, path: str) -> dict:
    req = urllib.request.Request(f"{cfg.cse_http}/{path}", headers={
        "X-M2M-Origin": "CAdmin", "X-M2M-RI": uuid.uuid4().hex[:12], "X-M2M-RVI": "5",
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def sensors(cfg: Config) -> list[dict]:
    q = urllib.parse.urlencode({"fu": 1, "ty": 2, "lbl": "app:farmnet"})
    uris = get(cfg, f"{cfg.cse_name}?{q}").get("m2m:uril", [])
    uris = [u.lstrip("/") for u in uris if not u.endswith("alert")]

    def latest(uri: str) -> dict:
        row = {"sensor": uri.rsplit("/", 1)[-1]}
        try:
            cin = get(cfg, f"{uri}/data/la").get("m2m:cin", {})
            row.update(json.loads(cin.get("con", "{}")) if cin.get("con", "").startswith("{")
                       else {"t": cin.get("con")})
            row["ct"] = cin.get("ct", "")
        except (OSError, ValueError):
            row["error"] = "no reading yet"
        return row

    with ThreadPoolExecutor(16) as pool:
        return sorted(pool.map(latest, uris), key=lambda r: r["sensor"])


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="2">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FarmNet</title>
<style>
body{{font:14px system-ui,sans-serif;margin:16px;color:#1d2433;background:#fff}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:#5b6475;margin:0 0 12px}}
table{{border-collapse:collapse;width:100%;max-width:900px}}
th,td{{padding:6px 10px;border-bottom:1px solid #e3e6ec;text-align:right}} th:first-child,td:first-child{{text-align:left}}
th{{font-weight:600;background:#f5f6f9}} .low{{color:#b42318;font-weight:600}}
@media (prefers-color-scheme:dark){{body{{background:#14171f;color:#e6e9ef}} th{{background:#1f2430}}
td,th{{border-color:#2c3240}} p{{color:#9aa3b5}}}}
</style></head><body>
<h1>FarmNet: {n} sensors</h1>
<p>Sensors write in <b>Protobuf over MQTT</b>; this page reads the same data from the oneM2M CSE as
<b>plain JSON over HTTP</b>. Updated {now} &middot; refreshes every 2 s.</p>
<table><tr><th>sensor</th><th>soil moisture %</th><th>temperature °C</th><th>humidity %</th>
<th>battery %</th><th>written (UTC)</th></tr>{rows}</table></body></html>"""


def render(cfg: Config) -> str:
    try:
        rows = sensors(cfg)
    except OSError as e:
        return f"<p>CSE not reachable at {html.escape(cfg.cse_http)}: {html.escape(str(e))}</p>"
    out = []
    for r in rows:
        soil = r.get("soil", "")
        cls = ' class="low"' if isinstance(soil, (int, float)) and soil < 15 else ""
        ct = r.get("ct", "")
        when = f"{ct[9:11]}:{ct[11:13]}:{ct[13:15]}" if len(ct) >= 15 else ""
        out.append(f"<tr><td>{html.escape(r['sensor'])}</td><td{cls}>{soil}</td><td>{r.get('t', '')}</td>"
                   f"<td>{r.get('h', '')}</td><td>{r.get('bat', '')}</td><td>{when}</td></tr>")
    return PAGE.format(n=len(rows), rows="".join(out) or "<tr><td colspan=6>no sensors yet</td></tr>",
                       now=datetime.now(timezone.utc).strftime("%H:%M:%S UTC"))


def main(args: argparse.Namespace) -> None:
    cfg = Config.from_env()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/api":
                body, ctype = json.dumps(sensors(cfg)).encode(), "application/json"
            else:
                body, ctype = render(cfg).encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: object) -> None:
            pass

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"FarmNet dashboard on http://0.0.0.0:{args.port}  (CSE {cfg.cse_http})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("dashboard", help="FarmNet dashboard: reads the CSE over HTTP/JSON",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8090)
    p.set_defaults(func=main)
