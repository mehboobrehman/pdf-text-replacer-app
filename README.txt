PDF Text Replacer - Portable
============================

This is a portable bundle. It can be copied to another Windows machine and run from there.

First time setup:
1. Install Python 3.11+ from python.org
2. Double-click setup.bat
3. Wait for pip install to finish

To run:
- Double-click run.bat
- Browser opens automatically to http://127.0.0.1:5173

Optional OCR:
- install Tesseract OCR from: https://github.com/UB-Mannheim/tesseract
- Enable OCR mode in the app UI

Files included:
- server.py - local web server
- scripts/replace_pdf_text.py - PDF text engine
- index.html, styles.css, app.js - UI
- setup.bat - install dependencies
- run.bat - start the app silently
- launch.ps1 - hidden launcher + browser open
- requirements.txt - python dependencies
