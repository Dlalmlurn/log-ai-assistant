from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


OUTPUT = Path(os.getenv("WEBHOOK_OUTPUT", "/var/log/webhook/deliveries.jsonl"))
FAIL_FIRST_N = int(os.getenv("WEBHOOK_FAIL_FIRST_N", "1"))
attempts: dict[str, int] = {}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        key = self.headers.get("Idempotency-Key", "")
        attempts[key] = attempts.get(key, 0) + 1
        if attempts[key] <= FAIL_FIRST_N:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"retry")
            return

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(body.decode("utf-8"))
        with OUTPUT.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"idempotency_key": key, "payload": payload}, ensure_ascii=False) + "\n")
        self.send_response(204)
        self.end_headers()

    def log_message(self, _format: str, *_args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
