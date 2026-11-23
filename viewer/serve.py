"""Tiny local server for the log viewer (stdlib only).

    python viewer/serve.py [--port 8765] [--logs experiments/logs]

Routes:
    /                    -> viewer/index.html
    /api/logs            -> JSON list of *.jsonl in the logs dir: [{name, size, mtime}]
    /api/log?name=X&from=N
                         -> bytes of X starting at byte offset N, cut at the last complete line.
                            Header X-Next-Offset tells the client where to resume (live tail).
"""
import argparse
import json
import os
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]  # Windows consoles default to cp1252
HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--logs", default=str(HERE.parent / "experiments" / "logs"))
ap.add_argument("--open", action="store_true", help="open the page in the default browser")
args = ap.parse_args()
LOGS = Path(args.logs).resolve()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, format, *args):  # noqa: A002 - keep the console quiet (polling every few seconds)
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/logs":
            files = []
            if LOGS.is_dir():
                for p in LOGS.glob("*.jsonl"):
                    st = p.stat()
                    files.append({"name": p.name, "size": st.st_size, "mtime": st.st_mtime})
            files.sort(key=lambda f: -f["mtime"])
            return self.send_json({"dir": str(LOGS), "files": files})
        if u.path == "/api/log":
            q = parse_qs(u.query)
            name = os.path.basename(q.get("name", [""])[0])
            p = LOGS / name
            if not name.endswith(".jsonl") or not p.is_file():
                return self.send_json({"error": "not found"}, 404)
            start = int(q.get("from", ["0"])[0] or 0)
            size = p.stat().st_size
            if start > size:  # file was truncated/overwritten by a new run
                start = 0
            with open(p, "rb") as f:
                f.seek(start)
                data = f.read()
            cut = data.rfind(b"\n") + 1  # only complete lines
            data = data[:cut]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Start", str(start))
            self.send_header("X-Next-Offset", str(start + cut))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Log viewer: {url}  (logs: {LOGS})  Ctrl+C để dừng", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
