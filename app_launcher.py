#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import threading
import socket
import time
import subprocess
import webbrowser
import http.server

# Static imports for PyInstaller detection
try:
    import fitz
    import fitz._fitz
    import pymupdf
except ImportError:
    pass

try:
    import PIL
    from PIL import Image
except ImportError:
    pass

try:
    import pytesseract
except ImportError:
    pass

try:
    import webview
except ImportError:
    pass

# Ensure scripts is in sys.path and replace_pdf_text is bundled
_launcher_dir = os.path.dirname(os.path.abspath(__file__))
_scripts_dir = os.path.join(_launcher_dir, "scripts")
if os.path.exists(_scripts_dir) and _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

try:
    import replace_pdf_text
except ImportError:
    try:
        from scripts import replace_pdf_text
    except ImportError:
        pass

# Add current directory to sys.path so we can import server.py
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from server import Handler, APP_DIR, UPLOAD_DIR, OUTPUT_DIR
except ImportError as e:
    print(f"Error: Could not import server.py: {e}")
    sys.exit(1)

def get_free_port():
    """Find a free available port by binding to port 0."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]
    except Exception:
        return 8000  # Fallback to 8000 if port 0 binding fails

def run_server(port):
    """Run the HTTP server on the specified port."""
    # Ensure directories exist
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Set PORT environment variable so server.py picks it up if it were to run separately,
    # though here we are using the Handler class directly which uses the port we pass.
    os.environ["PORT"] = str(port)
    os.environ["NO_BROWSER"] = "1"
    
    server_address = ("127.0.0.1", port)
    try:
        # Use ThreadingHTTPServer to handle multiple requests concurrently
        with http.server.ThreadingHTTPServer(server_address, Handler) as httpd:
            print(f"Backend server started at http://127.0.0.1:{port}", flush=True)
            httpd.serve_forever()
    except Exception as e:
        print(f"Server error: {e}", flush=True)

def main():
    # Detect port
    port = get_free_port()
    url = f"http://127.0.0.1:{port}/"
    
    # Start server in a background daemon thread
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()
    
    # Give the server a moment to initialize
    time.sleep(1.0) # Increased to 1s to be safer
    
    print(f"Application URL: {url}", flush=True)
    
    launched = False
    
    # Attempt 1: pywebview
    try:
        import webview
        print("Attempting to launch pywebview window...", flush=True)
        # Create a window with a reasonable default size
        window = webview.create_window(
            "PDF Text Replacer", 
            url, 
            width=1100, 
            height=850,
            min_size=(800, 600)
        )
        webview.start()
        launched = True
    except (ImportError, Exception) as e:
        print(f"pywebview launch failed or not available: {e}", flush=True)

    if not launched:
        # Attempt 2: Edge App Mode (Chromium based windowing)
        edge_paths = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        
        edge_bin = None
        for p in edge_paths:
            if os.path.exists(p):
                edge_bin = p
                break
        
        if edge_bin:
            print(f"Attempting to launch Edge in --app mode: {edge_bin}", flush=True)
            try:
                subprocess.Popen([edge_bin, f"--app={url}"])
                launched = True
            except Exception as e:
                print(f"Edge launch failed: {e}", flush=True)
        
        if not launched:
            # Attempt 3: Default System Browser
            print(f"Falling back to default system browser: {url}", flush=True)
            try:
                webbrowser.open(url)
                launched = True
            except Exception as e:
                print(f"Failed to open browser: {e}", flush=True)
                print(f"Please open this URL manually: {url}", flush=True)
        
        # If we launched via subprocess (Edge) or Browser, the main thread must stay alive
        if launched:
            print("Launcher active. Press Ctrl+C to stop.", flush=True)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping application...", flush=True)

if __name__ == "__main__":
    main()
