"""Optional developer preview: serves only the generated HTML on loopback."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()
artifact = Path(__file__).resolve().parents[1] / "pmut-haptics.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/pmut-haptics.html"}:
            self.send_error(404)
            return
        content = artifact.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'unsafe-inline' blob:; "
                         "style-src 'unsafe-inline'; worker-src blob:; "
                         "img-src data: blob:; connect-src 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(content)


print(f"Single-artifact preview: http://127.0.0.1:{args.port}", flush=True)
ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
