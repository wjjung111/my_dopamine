"""우진 캘린더 웹 서버. http://127.0.0.1:8765 에서 화면과 JSON API를 제공한다."""
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db

HOST, PORT = "127.0.0.1", 8765
STATIC = Path(__file__).resolve().parent / "static"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, body, ctype="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _route(self, method: str):
        u = urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if not parts or parts[0] != "api":
                return self._static(u.path)
            con = db.connect()
            try:
                res = self._api(con, method, parts[1:], qs)
            finally:
                con.close()
            self._send(200, res)
        except (ValueError, KeyError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # noqa
            self._send(500, {"error": repr(e)})

    def _api(self, con, method, p, qs):
        if p == ["rev"]:
            return {"rev": db.revision(con)}
        if p == ["calendars"] and method == "GET":
            return db.list_calendars(con)
        if len(p) == 2 and p[0] == "calendars" and method == "PATCH":
            return db.update_calendar(con, p[1], self._json())
        if p == ["items"]:
            if method == "GET":
                return {"rev": db.revision(con), "items": db.list_items(con, qs.get("from"), qs.get("to"))}
            if method == "POST":
                return db.create_item(con, self._json())
        if len(p) == 2 and p[0] == "items":
            iid = int(p[1])
            if method == "GET":
                return db.get_item(con, iid)
            if method == "PATCH":
                return db.update_item(con, iid, self._json())
            if method == "DELETE":
                return db.delete_item(con, iid)
        raise KeyError("없는 주소")

    def _static(self, path: str):
        f = (STATIC / (path.lstrip("/") or "index.html")).resolve()
        if STATIC not in f.parents and f != STATIC / "index.html" or not f.is_file():
            f = STATIC / "index.html"
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PATCH(self):
        self._route("PATCH")

    def do_DELETE(self):
        self._route("DELETE")


def main():
    try:
        srv = ThreadingHTTPServer((HOST, PORT), H)
    except OSError:
        print("이미 실행 중입니다.")
        return
    db.connect().close()
    print(f"우진 캘린더: http://{HOST}:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
