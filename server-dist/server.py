"""
Smart Review Portal - Data Server
portal-data.json HTTP file server.
Serves version data for the portal exe clients.

사용법:
  python server.py
  python server.py --port 9090
"""
import os
import sys
import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

def get_exe_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = get_exe_dir()
DATA_FILE = os.path.join(SCRIPT_DIR, "portal-data.json")
HTML_FILE = os.path.join(SCRIPT_DIR, "portal.html")
ANALYTICS_FILE = os.path.join(SCRIPT_DIR, "analytics.json")

VALID_SITES = {"KYK", "KYA", "KYA-MX", "JKY", "KYSEA", "KYV", "KYE", "KYC", "KYTW", "AES"}
VALID_ACTIONS = {"launch", "download"}


def load_analytics():
    if os.path.isfile(ANALYTICS_FILE):
        with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"events": []}


def save_analytics(data):
    with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class PortalDataHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ("/portal-data.json", "/"):
            self._serve_json()
        elif self.path == "/portal.html":
            self._serve_html()
        elif self.path == "/health":
            self._send_response(200, "application/json", json.dumps({"status": "ok"}))
        elif self.path == "/api/analytics":
            self._serve_analytics()
        else:
            self._send_response(404, "text/plain", "Not Found")

    def do_POST(self):
        if self.path == "/portal-data.json":
            self._upload_json()
        elif self.path == "/portal.html":
            self._upload_html()
        elif self.path == "/api/event":
            self._receive_event()
        else:
            self._send_response(404, "text/plain", "Not Found")

    def do_DELETE(self):
        if self.path == "/api/analytics":
            save_analytics({"events": []})
            self._send_response(200, "application/json", json.dumps({"status": "reset"}))
        else:
            self._send_response(404, "text/plain", "Not Found")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _upload_json(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._send_response(200, "application/json", json.dumps({"status": "updated"}))
        except json.JSONDecodeError:
            self._send_response(400, "text/plain", "Invalid JSON")

    def _receive_event(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            self._send_response(400, "text/plain", "Invalid JSON")
            return

        site = event.get("site", "")
        action = event.get("action", "")
        if site not in VALID_SITES or action not in VALID_ACTIONS:
            self._send_response(400, "application/json",
                                json.dumps({"error": "Invalid site or action"}))
            return

        record = {
            "site": site,
            "action": action,
            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }
        sw = event.get("sw")
        if sw and action == "download":
            record["sw"] = str(sw)[:100]

        analytics = load_analytics()
        analytics["events"].append(record)
        save_analytics(analytics)
        self._send_response(200, "application/json", json.dumps({"status": "ok"}))

    def _serve_analytics(self):
        analytics = load_analytics()
        self._send_response(200, "application/json; charset=utf-8",
                            json.dumps(analytics, ensure_ascii=False))

    def _serve_json(self):
        if not os.path.isfile(DATA_FILE):
            self._send_response(404, "text/plain", "portal-data.json not found")
            return
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = f.read()
        self._send_response(200, "application/json; charset=utf-8", data)

    def _serve_html(self):
        if not os.path.isfile(HTML_FILE):
            self._send_response(404, "text/plain", "portal.html not found")
            return
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            html = f.read()
        self._send_response(200, "text/html; charset=utf-8", html)

    def _upload_html(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(body)
        self._send_response(200, "application/json", json.dumps({"status": "updated"}))

    def _send_response(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.client_address[0]} - {format % args}")


def main():
    parser = argparse.ArgumentParser(description="Smart Review Portal Data Server")
    parser.add_argument("--port", type=int, default=9090, help="Port (default: 8080)")
    args = parser.parse_args()

    if not os.path.isfile(DATA_FILE):
        print(f"[WARNING] {DATA_FILE} not found. Copy portal-data.json to this folder.")

    server = HTTPServer(("0.0.0.0", args.port), PortalDataHandler)
    print("=" * 50)
    print("  Smart Review Portal - Data Server")
    print("=" * 50)
    print(f"  Port: {args.port}")
    print(f"  Data: {DATA_FILE}")
    print(f"  URL:  http://localhost:{args.port}/portal-data.json")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 50)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
