# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('index.html', '.'), ('app.js', '.'), ('styles.css', '.'), ('scripts', 'scripts')],
    hiddenimports=[
        'fitz',
        'fitz._fitz',
        'pymupdf',
        'PyMuPDF',
        'PIL',
        'PIL.Image',
        'pytesseract',
        'replace_pdf_text',
        'scripts',
        'scripts.replace_pdf_text',
        'webview',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PDFTextReplacer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    version='version_info.txt',
)
