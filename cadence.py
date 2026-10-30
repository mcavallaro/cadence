#!/usr/bin/env python3
"""
Cadence: tap a button to mark a moment (time X), add a note, and get a schedule of
X+N h, X+2N h, ... (covering 24 hours) with an alarm option for each. You choose N
(default 3 hours). See README.md.

Every recorded time and note is saved on the PC in  cadence_data.json
(next to this script). You can also download them as CSV from /export.csv.

Works over both  http://<pc-ip>:8000  and  https://<pc-ip>:8000  (same port).
For https it makes a self-signed certificate (needs the "openssl" command or
"pip install cryptography"); your browser will show a one-time warning.

Files: keep cadence.py (server) and cadence.html (the page) together.

Run:   python cadence.py          (or add a port:  python cadence.py 8080)
Needs: Python 3.6+ (no extra packages). Phone and PC must be on the same Wi-Fi.
"""
import csv
import http.server
import io
import json
import os
import socket
import shutil
import socketserver
import ssl
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta

# Default port 8000 (Pi-hole uses 80/443, so no clash). Change it with:  python cadence.py 8080
try:
    PORT = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8000))
except ValueError:
    PORT = 8000
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cadence_data.json")
LOCK = threading.Lock()
BASE = os.path.dirname(os.path.abspath(__file__))
CERT_FILE = os.path.join(BASE, "cadence_cert.pem")
KEY_FILE = os.path.join(BASE, "cadence_key.pem")
IP_FILE = os.path.join(BASE, "cadence_cert.ip")
PAGE_FILE = os.path.join(BASE, "cadence.html")   # the web page (HTML/CSS/JS)


def clean_h(v, default=3.0):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return round(min(24.0, max(0.5, v)), 2)


# ---------------------------------------------------------------- storage
def read_entries():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def write_entries(entries):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)


def visible(entries):
    """Entries still shown on the page. 'Cleared' ones stay in the file on disk."""
    return [e for e in entries if not e.get("cleared")]


def to_csv(entries):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["recorded_at_local", "interval_hours", "note", "cleared_from_page"])
    for e in sorted(entries, key=lambda e: e["x"]):
        local = datetime.utcfromtimestamp(e["x"] / 1000) - timedelta(minutes=e.get("tz", 0))
        w.writerow([local.strftime("%Y-%m-%d %H:%M:%S"), e.get("h", 3), e.get("note", ""), "yes" if e.get("cleared") else ""])
    return out.getvalue().encode("utf-8-sig")




MANIFEST = json.dumps({
    "name": "Cadence", "short_name": "Cadence", "start_url": "/", "display": "standalone",
    "background_color": "#f3f0e8", "theme_color": "#14213d",
    "icons": [{"src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' fill='%23e4572e'/%3E%3Ccircle cx='50' cy='50' r='28' fill='none' stroke='white' stroke-width='7'/%3E%3Cpath d='M50 32v20l13 8' fill='none' stroke='white' stroke-width='7' stroke-linecap='round'/%3E%3C/svg%3E",
               "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
})


# ---------------------------------------------------------------- server
class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/entries":
            with LOCK:
                self._json(visible(read_entries()))
        elif path == "/manifest.json":
            self._send(200, MANIFEST.encode("utf-8"), "application/manifest+json")
        elif path == "/export.csv":
            with LOCK:
                body = to_csv(read_entries())
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="cadence_history.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            try:
                with open(PAGE_FILE, "rb") as f:          # re-read each time: edit the page, just refresh
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"cadence.html not found next to the script", "text/plain")

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "bad request"}, 400)

        with LOCK:
            entries = read_entries()
            if self.path == "/api/add":
                x = int(data.get("x") or time.time() * 1000)
                entries.append({"id": uuid.uuid4().hex[:12], "x": x, "tz": int(data.get("tz", 0)),
                                "h": clean_h(data.get("h")), "note": ""})
            elif self.path == "/api/note":
                for e in entries:
                    if e["id"] == data.get("id"):
                        e["note"] = str(data.get("note", ""))[:5000]
            elif self.path == "/api/interval":
                for e in entries:
                    if e["id"] == data.get("id"):
                        e["h"] = clean_h(data.get("h"))
            elif self.path == "/api/delete":              # hide from the page, keep on disk
                for e in entries:
                    if e["id"] == data.get("id") and not e.get("cleared"):
                        e["cleared"] = int(time.time() * 1000)
            elif self.path == "/api/clear":               # hide everything, keep on disk
                now = int(time.time() * 1000)
                for e in entries:
                    if not e.get("cleared"):
                        e["cleared"] = now
            else:
                return self._json({"error": "not found"}, 404)
            write_entries(entries)
            self._json(visible(entries))

    def log_message(self, *args):
        pass


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def make_cert(ip):
    """Create a self-signed certificate for this PC's LAN IP. Returns True on success."""
    san = "subjectAltName=IP:%s,IP:127.0.0.1,DNS:localhost" % ip
    exe = shutil.which("openssl")
    if exe:
        base = [exe, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", KEY_FILE,
                "-out", CERT_FILE, "-days", "825", "-subj", "/CN=cadence"]
        for extra in (["-addext", san], []):          # older OpenSSL has no -addext
            try:
                subprocess.run(base + extra, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except (OSError, subprocess.CalledProcessError):
                pass
    try:
        import datetime as dt
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "cadence")])
        now = dt.datetime.utcnow()
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=825))
                .add_extension(x509.SubjectAlternativeName([
                    x509.IPAddress(ipaddress.ip_address(ip)),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.DNSName("localhost")]), critical=False)
                .sign(key, hashes.SHA256()))
        with open(KEY_FILE, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                      serialization.NoEncryption()))
        with open(CERT_FILE, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        return True
    except Exception:
        return False


def tls_context(ip):
    try:
        with open(IP_FILE) as f:
            have = os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE) and f.read().strip() == ip
    except OSError:
        have = False
    if not have:
        if not make_cert(ip):
            return None
        with open(IP_FILE, "w") as f:
            f.write(ip)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    except (ssl.SSLError, OSError):
        return None
    return ctx


class Server(socketserver.ThreadingTCPServer):
    """One port, two protocols: a TLS handshake (first byte 0x16) is served as https, anything else as http."""
    allow_reuse_address = True
    daemon_threads = True
    tls = None

    def finish_request(self, request, client_address):
        conn = request
        try:
            request.settimeout(10)
            first = request.recv(1, socket.MSG_PEEK)
            if not first:
                return
            if first == b"\x16":
                if not self.tls:
                    return
                conn = self.tls.wrap_socket(request, server_side=True)
            conn.settimeout(30)
            self.RequestHandlerClass(conn, client_address, self)
        except (OSError, ssl.SSLError):
            pass
        finally:
            if conn is not request:
                try:
                    conn.close()
                except OSError:
                    pass

    def handle_error(self, request, client_address):
        pass


if __name__ == "__main__":
    old_data = os.path.join(BASE, "three_hour_data.json")      # data file from the earlier version
    if os.path.exists(old_data) and not os.path.exists(DATA_FILE):
        os.replace(old_data, DATA_FILE)
    if not os.path.exists(PAGE_FILE):
        sys.exit("Missing cadence.html. Put it in the same folder as this script.")
    ip = lan_ip()
    try:
        srv = Server(("0.0.0.0", PORT), Handler)
    except OSError:
        print(f"\nPort {PORT} is already in use by another program (Pi-hole uses 80 and 443).")
        print("Pick a free port, e.g.:  python cadence.py 8080")
        sys.exit(1)
    with srv:
        srv.tls = tls_context(ip)
        print("\nRunning. Open this on your phone (same Wi-Fi):")
        print(f"    http://{ip}:{PORT}")
        if srv.tls:
            print(f"    https://{ip}:{PORT}   (one-time browser warning: Advanced > Proceed)")
        else:
            print("    (https is off: install OpenSSL, or run  pip install cryptography)")
        print(f"\nYour data is saved in: {DATA_FILE}")
        print("Press Ctrl+C to stop.")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
