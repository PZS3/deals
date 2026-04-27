#!/usr/bin/env python3
"""
Prazwal's Deal Finder — HTTP Server
Serves the dashboard + handles refresh requests.
"""

import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from scraper import run_scraper

BASE_DIR = Path(__file__).parent
PORT = 8090


class DealHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_POST(self):
        if self.path == "/refresh":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            # Send immediate acknowledgment
            self.wfile.write(json.dumps({"status": "scraping"}).encode())
            self.wfile.flush()

            # Run scraper in background
            def bg_scrape():
                try:
                    run_scraper()
                except Exception as e:
                    print(f"Scraper error: {e}")

            t = threading.Thread(target=bg_scrape, daemon=True)
            t.start()
        else:
            self.send_error(404)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/deals":
            deals_path = BASE_DIR / "deals.json"
            if deals_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(deals_path.read_bytes())
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"last_updated": None, "total_deals": 0, "deals": []}).encode())
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
    print(f"Access from TV/phone: http://192.168.1.12:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
