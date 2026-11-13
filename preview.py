"""Serves docs/ for previewing.

    python preview.py           then open http://localhost:8000/

It does what `python -m http.server` does, with one difference: every answer
tells the browser to ask again before it reuses a file. Without that a browser
goes on showing its own copy of a picture, sometimes for hours, after a build
has put a new picture at the same address. A reload then shows the new one.

The site is served to this computer only.
"""

import functools
import http.server
import os
import sys

PORT = 8000
DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        http.server.SimpleHTTPRequestHandler.end_headers(self)


def main():
    handler = functools.partial(Handler, directory=DOCS)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    print("Serving docs/ at http://localhost:%d/ (Ctrl+C stops it)" % PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
