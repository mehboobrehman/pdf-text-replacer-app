# Project Decisions

Architectural and design decisions made during development.
All agents should read this before starting work and log new decisions here.

## Packaging: PyInstaller with pywebview/Edge-app launcher and frozen resource path resolution
**When**: 2026-08-19 09:11:56

Use app_launcher.py as entrypoint with pywebview windowing and Edge --app fallback. Embedded HTTP server runs on dynamic available port. Server path resolution supports PyInstaller sys._MEIPASS for static files and sys.executable parent dir for writable upload/output folders. Direct module call to replace_text_in_pdf handles PDF operations cleanly inside frozen exe.

**Impact**: Executable build pipeline, app launcher, server path resolution, desktop windowing

## Packaging: Implement Code Signing and Manifest Hardening for Windows SAC Compliance
**When**: 2026-11-13 10:33:37

SAC enforces code signing for executables. To resolve blocking, code signing is mandatory, supplemented by manifest hardening and alternative distribution methods.

**Impact**: Packaging, executable signing, and distribution strategy.

## Fix recursive filename timestamp compounding in server.py and replace_pdf_text.py
**When**: 2026-11-13 14:44:15

To prevent recursive filename timestamp compounding (e.g. 20261113_132340_20261113_132335_..._edited.pdf) which exceeds Windows MAX_PATH limits and causes PyMuPDF fz_error_system errors, we strip leading timestamp prefixes (^\d{8}_\d{6}_)+ and trailing _edited suffixes from the base name before prepending a single fresh timestamp and _edited.pdf.

**Impact**: server.py and scripts/replace_pdf_text.py filename generation logic
