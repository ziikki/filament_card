#!/usr/bin/env python3
"""
Bambu Lab Filament Card Studio - Web Server
Runs a local web application to extract filament details, preview the card, and generate .3MF files.
"""
import base64
import json
import os
import re
import tempfile
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

import cv2
import make_filament_card as mfc
import extractor

PORT = 8088
HERE = os.path.dirname(os.path.abspath(__file__))

HTML_FALLBACK = b"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Bambu Lab Filament Card Studio</title></head>
<body style="font-family: sans-serif; padding: 40px; text-align: center;">
  <h2>Bambu Lab Filament Card Studio</h2>
  <p>Static index.html not found. Please ensure index.html exists in the repository root directory.</p>
</body>
</html>"""

class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass

class FilamentStudioHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Concise logging
        print(f"[{self.command}] {self.path} - {args[0]}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html", "/en.html", "/en"]:
            idx_file = os.path.join(HERE, "index.html")
            if os.path.exists(idx_file):
                with open(idx_file, "rb") as f:
                    content = f.read()
            else:
                content = HTML_FALLBACK
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path in ["/zh.html", "/zh"]:
            zh_file = os.path.join(HERE, "zh.html")
            if os.path.exists(zh_file):
                with open(zh_file, "rb") as f:
                    content = f.read()
            else:
                content = HTML_FALLBACK
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path in ["/filament_db.json", "/api/database"]:
            db_path = os.path.join(HERE, "filament_db.json")
            if os.path.exists(db_path):
                with open(db_path, "rb") as f:
                    content = f.read()
            else:
                content = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path in ["/card_template.3mf", "/template/card_template.3mf"]:
            tmpl_path = os.path.join(HERE, "card_template.3mf")
            if not os.path.exists(tmpl_path):
                tmpl_path = os.path.join(HERE, "template", "card_template.3mf")
            if os.path.exists(tmpl_path):
                with open(tmpl_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        elif path.startswith("/examples/"):
            rel_file = urllib.parse.unquote(path.lstrip("/"))
            file_path = os.path.join(HERE, rel_file)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                content_type = "image/png" if file_path.endswith(".png") else "application/octet-stream"
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"

        try:
            body = json.loads(post_data)
        except Exception:
            body = {}

        if path == "/api/extract":
            url = body.get("url", "")
            res = extractor.extract_from_url(url)
            self.send_response(200 if res.get("success") else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        elif path == "/api/preview":
            material = body.get("material", "PLA WOOD")
            color = body.get("color", "White Oak")
            code = body.get("code", "(13106)")
            hex_color = body.get("hex", "#D6CCA3")
            swatch_d = float(body.get("swatch_d", 7.0))
            thicken = bool(body.get("thicken", False))

            try:
                bgr_img, warns, stroke_info = mfc.render_preview_image(
                    material=material,
                    color=color,
                    code=code,
                    hex_color=hex_color,
                    swatch_d=swatch_d,
                    thicken=thicken
                )
                ret, buf = cv2.imencode(".png", bgr_img)
                b64 = base64.b64encode(buf).decode("ascii")
                data_uri = f"data:image/png;base64,{b64}"

                resp = {
                    "success": True,
                    "preview_base64": data_uri,
                    "warnings": warns,
                    "stroke_info": stroke_info
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        elif path == "/api/generate":
            material = body.get("material", "PLA WOOD")
            color = body.get("color", "White Oak")
            code = body.get("code", "(13106)")
            hex_color = body.get("hex", "#D6CCA3")
            relief = float(body.get("relief", 0.5))
            swatch_d = float(body.get("swatch_d", 7.0))
            thicken = bool(body.get("thicken", False))

            try:
                with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as tmp:
                    tmp_out = tmp.name

                meta = mfc.generate_card(
                    material=material,
                    color=color,
                    code=code,
                    hex_color=hex_color,
                    relief=relief,
                    out_path=tmp_out,
                    swatch_d=swatch_d,
                    thicken=thicken,
                    preview=False
                )

                with open(tmp_out, "rb") as f:
                    file_bytes = f.read()

                try:
                    os.unlink(tmp_out)
                except Exception:
                    pass

                clean_col = re.sub(r'[\\/:*?"<>|\s]+', '_', color).strip('_')
                filename = f"耗材样本卡_{clean_col}.3mf"
                # UTF-8 encoded filename in RFC 5987 format
                quoted_fn = urllib.parse.quote(filename)

                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")
                self.send_header("Content-Disposition", f'attachment; filename="{quoted_fn}"; filename*=UTF-8\'\'{quoted_fn}')
                self.send_header("Content-Length", str(len(file_bytes)))
                self.end_headers()
                self.wfile.write(file_bytes)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=PORT):
    server_address = ('127.0.0.1', port)
    httpd = ThreadingSimpleServer(server_address, FilamentStudioHandler)
    print(f"🚀 Bambu Lab Filament Card Studio running at http://localhost:{port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
