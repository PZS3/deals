#!/usr/bin/env python3
"""
Prazwal's Deal Finder — HTTP Server
Serves the dashboard + handles refresh requests.
"""

import json
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from scraper import run_scraper

BASE_DIR = Path(__file__).parent
PORT = 8090

# Only one scrape at a time — a second /refresh while one is running
# gets "already_running" instead of a duplicate scraper racing on deals.json.
_scrape_lock = threading.Lock()


def _scrape_in_progress():
    if _scrape_lock.acquire(blocking=False):
        _scrape_lock.release()
        return False
    return True


def _bg_scrape():
    with _scrape_lock:
        try:
            run_scraper()
        except Exception as e:
            print(f"Scraper error: {e}")


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "localhost"


class DealHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def _send_json(self, payload):
        body = json.dumps(payload).encode() if isinstance(payload, dict) else payload
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/refresh":
            if _scrape_in_progress():
                self._send_json({"status": "already_running"})
                return
            self._send_json({"status": "scraping"})
            threading.Thread(target=_bg_scrape, daemon=True).start()
        else:
            self.send_error(404)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/deals":
            deals_path = BASE_DIR / "deals.json"
            if deals_path.exists():
                self._send_json(deals_path.read_bytes())
            else:
                self._send_json({"last_updated": None, "total_deals": 0, "deals": []})
        elif path == "/api/status":
            self._send_json({"scraping": _scrape_in_progress()})
        else:
            super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format, *args):
        # Suppress noisy logs for static files
        if "/api/" in str(args[0]) or "POST" in str(args[0]):
            super().log_message(format, *args)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), DealHandler)
    print(f"Deal Finder running at http://0.0.0.0:{PORT}")
    print(f"Access from TV/phone: http://{_lan_ip()}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
