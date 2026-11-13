# -*- coding: utf-8 -*-
#!/usr/bin/env python3
import contextlib
import email
import email.policy
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import datetime

# Static imports for PyInstaller detection
try:
    import fitz
    import fitz._fitz
    import pymupdf
except ImportError:
    fitz = None

try:
    import PIL
    from PIL import Image
except ImportError:
    PIL = None
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    reconfig_out = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfig_out):
        reconfig_out(line_buffering=True)
    reconfig_err = getattr(sys.stderr, "reconfigure", None)
    if callable(reconfig_err):
        reconfig_err(line_buffering=True)
except Exception:
    pass

IS_FROZEN = getattr(sys, "frozen", False)
EXE_DIR = os.path.dirname(os.path.abspath(sys.executable)) if IS_FROZEN else os.path.dirname(os.path.abspath(__file__))
if IS_FROZEN:
    APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    UPLOAD_DIR = os.path.join(EXE_DIR, "uploaded")
    OUTPUT_DIR = os.path.join(EXE_DIR, "output")
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_DIR = os.path.join(APP_DIR, "uploaded")
    OUTPUT_DIR = os.path.join(APP_DIR, "output")

SKILL_SCRIPT = os.path.join(APP_DIR, "scripts", "replace_pdf_text.py")
if not os.path.exists(SKILL_SCRIPT) and not IS_FROZEN:
    SKILL_SCRIPT = os.path.join(
        r"C:\Users\mehboob.rehman\AppData\Local\com.sarfrazai.agentdesk\stable\skills\pdf-text-replacer\scripts",
        "replace_pdf_text.py",
    )

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Add scripts directory to sys.path
scripts_dir = os.path.join(APP_DIR, "scripts")
scripts_dir_alt = os.path.join(EXE_DIR, "scripts")
# In bundled executable, the 'scripts' folder is inside _MEIPASS
if IS_FROZEN:
    scripts_dir_meipass = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "scripts")
else:
    scripts_dir_meipass = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")

# Check all possible locations
for d in [scripts_dir, scripts_dir_alt, scripts_dir_meipass]:
    if os.path.exists(d) and d not in sys.path:
        sys.path.insert(0, d)
        print(f"DEBUG: Added {d} to sys.path", file=sys.stderr, flush=True)

IMPORT_ERROR_DETAILS = None

try:
    try:
        from replace_pdf_text import (  # type: ignore # pyright: ignore[reportMissingImports]
            replace_text_in_pdf,
            scan_pdf_text,
            scan_pdf_text_ocr,
        )
    except (ImportError, ModuleNotFoundError):
        from scripts.replace_pdf_text import (  # type: ignore # pyright: ignore[reportMissingImports]
            replace_text_in_pdf,
            scan_pdf_text,
            scan_pdf_text_ocr,
        )
    print("DEBUG: replace_pdf_text imported successfully", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    IMPORT_ERROR_DETAILS = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    print(f"DEBUG: Failed to import replace_pdf_text: {IMPORT_ERROR_DETAILS}", file=sys.stderr, flush=True)
    scan_pdf_text = None
    scan_pdf_text_ocr = None
    replace_text_in_pdf = None

ALLOWED_EXTENSIONS = {".pdf"}


def _is_allowed_pdf(name):
    _, ext = os.path.splitext(name.lower())
    if ext not in ALLOWED_EXTENSIONS:
        return False
    if not name or name.startswith("."):
        return False
    return True


def _parse_multipart(headers, rfile):
    content_type = headers.get("Content-Type", "")
    print(f"DEBUG: Content-Type: {content_type}", file=sys.stderr, flush=True)
    if "multipart/form-data" not in content_type:
        print(f"DEBUG: Content-Type does not contain multipart/form-data: {content_type}", file=sys.stderr, flush=True)
        raise ValueError("Invalid multipart content type")
    m = re.search(r"boundary=([^\s;]+)", content_type)
    if not m:
        print(f"DEBUG: Regex failed to find boundary in content_type: {content_type}", file=sys.stderr, flush=True)
        raise ValueError("Invalid multipart content type")
    boundary = m.group(1)
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]
    
    content_length = int(headers.get("Content-Length", "0"))
    print(f"DEBUG: Content-Length: {content_length}", file=sys.stderr, flush=True)
    if content_length <= 0:
        raise ValueError("Missing content length")
    
    raw = rfile.read(content_length)
    print(f"DEBUG: Read {len(raw)} bytes", file=sys.stderr, flush=True)

    boundary_bytes = ("--" + boundary).encode("utf-8")
    end_bytes = ("--" + boundary + "--").encode("utf-8")

    parts = []
    pos = 0
    data = raw
    while True:
        start = data.find(boundary_bytes, pos)
        if start == -1:
            break
        end = data.find(boundary_bytes, start + len(boundary_bytes))
        if end == -1:
            break
        part = data[start + len(boundary_bytes): end]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        elif part.endswith(b"\n"):
            part = part[:-1]
        parts.append(part)
        pos = end

    for part in parts:
        part = part.lstrip(b"\r\n")
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        part_headers_raw = part[:header_end]
        part_body = part[header_end + 4:]
        part_headers = email.message_from_bytes(part_headers_raw)
        disposition = part_headers.get("Content-Disposition", "")
        m2 = re.search(r'filename="?([^"\r\n;]+)"?', disposition)
        if m2:
            filename = m2.group(1)
            if filename.startswith('"') and filename.endswith('"'):
                filename = filename[1:-1]
            return part_body, filename

    raise ValueError("No file part found")


def _read_json_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    body = handler.rfile.read(length)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _write_json(handler, status, payload):
    payload_bytes = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(payload_bytes)))
    handler.end_headers()
    handler.wfile.write(payload_bytes)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=APP_DIR, **kwargs)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/api/health", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_HEAD()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/api/health", "/health"):
            payload = json.dumps({"status": "ok", "upload_dir": UPLOAD_DIR, "output_dir": OUTPUT_DIR}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path.startswith("/output/"):
            filename = urllib.parse.unquote(parsed.path[len("/output/"):])
            safe_name = os.path.basename(filename)
            if not safe_name:
                self.send_error(400, "Missing filename")
                return
            output_path = os.path.join(OUTPUT_DIR, safe_name)
            if not os.path.exists(output_path):
                self.send_error(404, "Output not found")
                return
            with open(output_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f"attachment; filename={safe_name}")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/upload":
            return self._handle_upload()
        if self.path == "/api/replace":
            return self._handle_replace()
        if self.path == "/api/preview":
            return self._handle_preview()
        self.send_error(404)
        return

    def _handle_upload(self):
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            _write_json(self, 400, {"error": "Expected multipart/form-data"})
            return

        try:
            file_bytes, filename = _parse_multipart(self.headers, self.rfile)
        except Exception as e:
            _write_json(self, 400, {"error": f"Failed to parse multipart: {e}"})
            return

        safe_filename = os.path.basename(filename)
        if not _is_allowed_pdf(safe_filename):
            _write_json(self, 400, {"error": "Only PDF files are allowed"})
            return

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_base, _ = os.path.splitext(safe_filename)
        save_name = f"{timestamp}_{safe_base}.pdf"
        save_path = os.path.join(UPLOAD_DIR, save_name)

        try:
            with open(save_path, "wb") as f:
                f.write(file_bytes)
        except Exception as e:
            _write_json(self, 500, {"error": f"Failed to save file: {e}"})
            return

        _write_json(self, 200, {"path": save_path, "filename": save_name})
        return

    def _handle_replace(self):
        data = _read_json_body(self)
        if data is None:
            self.send_error(400, "Invalid JSON")
            return

        pdf_path = data.get("pdf_path")
        search_text = data.get("search_text", "")
        replace_text = data.get("replace_text")

        if not pdf_path or not search_text or replace_text is None:
            _write_json(self, 400, {"error": "pdf_path, search_text, and replace_text are required"})
            return

        try:
            real_pdf = os.path.realpath(pdf_path)
            real_upload = os.path.realpath(UPLOAD_DIR)
            if os.path.commonpath([real_pdf, real_upload]) != real_upload:
                _write_json(self, 403, {"error": "Access denied: pdf_path outside upload directory"})
                return
        except Exception:
            _write_json(self, 400, {"error": "Invalid pdf_path"})
            return

        if not os.path.exists(pdf_path):
            _write_json(self, 404, {"error": f"PDF not found: {pdf_path}"})
            return

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        # Strip any leading timestamps and trailing _edited suffixes to prevent chaining on successive edits
        base_name = re.sub(r'^(\d{8}_\d{6}_)+', '', base_name)
        base_name = re.sub(r'(_edited(?:_\w+)*)+$', '', base_name)
        # Truncate base_name if excessively long to prevent path length limits (Windows MAX_PATH / PyMuPDF)
        if len(base_name) > 100:
            base_name = base_name[:100]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_name = f"{timestamp}_{base_name}_edited.pdf"
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, output_name)

        if replace_text_in_pdf is not None:
            # Direct in-process execution
            stdout_io = io.StringIO()
            stderr_io = io.StringIO()
            returncode = 0
            res_path = None
            try:
                with contextlib.redirect_stdout(stdout_io), contextlib.redirect_stderr(
                    stderr_io
                ):
                    res_path = replace_text_in_pdf(
                        pdf_path, search_text, replace_text, output_path
                    )
                    if not res_path:
                        returncode = 1
            except SystemExit as e:
                returncode = (
                    e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
                )
            except Exception as e:
                import traceback

                traceback.print_exc(file=stderr_io)
                returncode = 1

            response = {
                "stdout": stdout_io.getvalue(),
                "stderr": stderr_io.getvalue(),
                "returncode": returncode,
                "output": output_path if returncode == 0 else None,
                "output_name": output_name if returncode == 0 else None,
            }
            _write_json(self, 200, response)
            return
        
        if IS_FROZEN:
            err_msg = "Replacement unavailable: replace_pdf_text import failed"
            if IMPORT_ERROR_DETAILS:
                err_msg += f" Details: {IMPORT_ERROR_DETAILS.splitlines()[0]}"
            _write_json(self, 500, {"error": err_msg, "import_error": IMPORT_ERROR_DETAILS, "returncode": 1})
            return

        # Fallback to subprocess
        if not os.path.exists(SKILL_SCRIPT):
            _write_json(self, 500, {"error": f"Skill script not found: {SKILL_SCRIPT}"})
            return

        cmd = [
            sys.executable,
            SKILL_SCRIPT,
            pdf_path,
            search_text,
            replace_text,
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            _write_json(self, 500, {"error": f"Failed to run replacer: {e}"})
            return

        response = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "output": output_path if result.returncode == 0 else None,
            "output_name": output_name if result.returncode == 0 else None,
        }
        _write_json(self, 200, response)
        return

    def _handle_preview(self):
        data = _read_json_body(self)
        if data is None:
            self.send_error(400, "Invalid JSON")
            return

        pdf_path = data.get("pdf_path")
        mode = (data.get("mode") or "text").strip().lower()
        if not pdf_path:
            _write_json(self, 400, {"error": "pdf_path is required"})
            return

        try:
            real_pdf = os.path.realpath(pdf_path)
            real_upload = os.path.realpath(UPLOAD_DIR)
            if os.path.commonpath([real_pdf, real_upload]) != real_upload:
                _write_json(self, 403, {"error": "Access denied: pdf_path outside upload directory"})
                return
        except Exception:
            _write_json(self, 400, {"error": "Invalid pdf_path"})
            return

        if not os.path.exists(pdf_path):
            _write_json(self, 404, {"error": f"PDF not found: {pdf_path}"})
            return

        if mode == "ocr":
            if scan_pdf_text_ocr is None:
                err_msg = "OCR unavailable. Install pytesseract, Pillow, and Tesseract OCR."
                if IMPORT_ERROR_DETAILS:
                    err_msg += f" Details: {IMPORT_ERROR_DETAILS.splitlines()[0]}"
                _write_json(self, 500, {"error": err_msg, "import_error": IMPORT_ERROR_DETAILS})
                return
            try:
                preview = scan_pdf_text_ocr(pdf_path)
            except Exception as e:
                _write_json(self, 500, {"error": f"Failed to OCR PDF: {e}"})
                return

            _write_json(self, 200, preview)
            return

        # default text mode
        if scan_pdf_text is None:
            err_msg = "Preview unavailable: replace_pdf_text import failed"
            if IMPORT_ERROR_DETAILS:
                err_msg += f" Details: {IMPORT_ERROR_DETAILS.splitlines()[0]}"
            _write_json(self, 500, {"error": err_msg, "import_error": IMPORT_ERROR_DETAILS})
            return

        try:
            preview = scan_pdf_text(pdf_path)
        except Exception as e:
            _write_json(self, 500, {"error": f"Failed to scan PDF: {e}"})
            return

        _write_json(self, 200, preview)
        return


if __name__ == "__main__":
    try:
        reconfig_out = getattr(sys.stdout, "reconfigure", None)
        if callable(reconfig_out):
            reconfig_out(line_buffering=True)
        reconfig_err = getattr(sys.stderr, "reconfigure", None)
        if callable(reconfig_err):
            reconfig_err(line_buffering=True)
    except Exception:
        pass

    os.chdir(APP_DIR)
    host = os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
    raw_port = os.environ.get("PORT", "8000").strip()
    try:
        port = int(raw_port)
    except (ValueError, TypeError):
        port = 8000

    server_address = (host, port)
    with http.server.ThreadingHTTPServer(server_address, Handler) as httpd:
        print(f"PDF Text Replacer running at http://127.0.0.1:{port}", flush=True)
        print(f"Server listening on http://{host}:{port}", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()

        if not os.environ.get("NO_BROWSER") and not os.environ.get("PORT"):
            try:
                import threading
                threading.Thread(
                    target=lambda: (
                        __import__("time").sleep(1),
                        __import__("webbrowser").open(f"http://127.0.0.1:{port}/"),
                    ),
                    daemon=True,
                ).start()
            except Exception:
                pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.", flush=True)
            sys.stdout.flush()

