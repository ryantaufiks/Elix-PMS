"""A minimal Shelly Gen2+/Gen1 HTTP device for tests, with Digest SHA-256 auth like real firmware."""
import hashlib
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _h(text):
    return hashlib.sha256(text.encode()).hexdigest()


class FakeShelly:
    REALM = "shelly1g3-test"

    def __init__(self, password=None, gen1=False):
        self.password, self.gen1 = password, gen1
        self.calls, self.output = [], False
        self.nonce = secrets.token_hex(8)
        device = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, code, body, headers=None):
                data = json.dumps(body).encode()
                self.send_response(code)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authorised(self):
                if not device.password:
                    return True
                header = self.headers.get("Authorization", "")
                fields = dict(re.findall(r'(\w+)="?([^",]+)"?', header))
                if not header.startswith("Digest ") or fields.get("username") != "admin":
                    return False
                ha1 = _h(f"admin:{device.REALM}:{device.password}")
                ha2 = _h(f"{self.command}:{fields.get('uri')}")
                expected = _h(f"{ha1}:{fields.get('nonce')}:{fields.get('nc')}:{fields.get('cnonce')}:auth:{ha2}")
                return fields.get("response") == expected

            def do_POST(self):
                if device.gen1 or self.path != "/rpc":
                    return self._reply(404, {})
                if not self._authorised():
                    challenge = f'Digest qop="auth", realm="{device.REALM}", nonce="{device.nonce}", algorithm=SHA-256'
                    return self._reply(401, {}, {"WWW-Authenticate": challenge})
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                device.calls.append(body)
                if body["method"] == "Switch.Set":
                    device.output = body["params"]["on"]
                    return self._reply(200, {"id": body["id"], "result": {"was_on": False}})
                if body["method"] == "Switch.GetStatus":
                    return self._reply(200, {"id": body["id"], "result": {"id": 0, "output": device.output}})
                return self._reply(200, {"id": body["id"], "error": {"code": -103, "message": "No handler"}})

            def do_GET(self):
                if not device.gen1 or not self.path.startswith("/relay/"):
                    return self._reply(404, {})
                device.calls.append({"gen1": self.path})
                device.output = "turn=on" in self.path or device.output
                return self._reply(200, {"ison": device.output})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
