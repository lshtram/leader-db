"""Tiny streaming HTTP relay used in a separate Docker container."""

from __future__ import annotations

import http.client
import http.server
import os

_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class RelayHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        expected = f"Bearer {os.environ['RELAY_TOKEN']}"
        if self.headers.get("Authorization") != expected:
            self.send_error(401, "invalid relay token")
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        upstream = http.client.HTTPConnection(
            os.environ["UPSTREAM_HOST"],
            int(os.environ["UPSTREAM_PORT"]),
            timeout=900,
        )
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.casefold() not in _HOP_HEADERS
        }
        headers["Authorization"] = f"Bearer {os.environ['MINIMAX_API_KEY']}"
        headers["Connection"] = "close"
        upstream.request("POST", self.path, body=body, headers=headers)
        response = upstream.getresponse()
        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.casefold() not in _HOP_HEADERS:
                self.send_header(key, value)
        self.send_header("Connection", "close")
        self.end_headers()
        while chunk := response.read(65536):
            self.wfile.write(chunk)
            self.wfile.flush()
        upstream.close()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 8080), RelayHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
