#!/usr/bin/env python3
"""portia/scripts/static_server.py: the static gallery's local server: python's http.server plus HTTP Range requests,
so the evidence clips can seek (python -m http.server answers a Range request with the whole file, and Chromium then
treats the video as not seekable). GitHub Pages and the live app answer Range requests already.

    python scripts/static_server.py 5260 product/site          (binds 127.0.0.1)
"""
import os
import re
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        m = re.match(r"bytes=(\d*)-(\d*)$", (rng or "").strip())
        if not rng or not m or os.path.isdir(path):
            self._left = None
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        size = os.fstat(f.fileno()).st_size
        a, b = m.groups()
        start, end = (max(0, size - int(b)), size - 1) if a == "" else (int(a), min(size - 1, int(b) if b else size - 1))
        if start > end:
            f.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        f.seek(start)
        self._left = end - start + 1
        return f

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def copyfile(self, source, outputfile):
        left = getattr(self, "_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            buf = source.read(min(1 << 16, left))
            if not buf:
                break
            outputfile.write(buf)
            left -= len(buf)

    def log_message(self, *args):                       # quiet: the recorder fetches hundreds of files
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5260
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    ThreadingHTTPServer(("127.0.0.1", port), partial(RangeHandler, directory=root)).serve_forever()


if __name__ == "__main__":
    main()
