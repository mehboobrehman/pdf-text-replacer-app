#!/usr/bin/env python3
import json
import sys, os, fitz, shutil, re
from datetime import datetime
from PIL import Image

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    OCR_AVAILABLE = False


def get_tesseract_cmd():
    """
    Locates the Tesseract OCR executable by searching standard paths,
    environment variables, portable application folders, user local appdata,
    and system installations without requiring admin privileges.
    Returns: (tesseract_path, checked_locations)
    """
    checked = []

    # 1. Environment variables
    for env_var in ["TESSERACT_CMD", "TESSERACT_PATH"]:
        val = os.environ.get(env_var)
        if val:
            checked.append(f"{env_var}={val}")
            if os.path.isfile(val):
                return val, checked
            alt = os.path.join(val, "tesseract.exe")
            checked.append(alt)
            if os.path.isfile(alt):
                return alt, checked

    # 2. Portable directory next to executable or _MEIPASS
    dirs_to_check = []
    if getattr(sys, 'frozen', False):
        dirs_to_check.append(os.path.dirname(os.path.abspath(sys.executable)))
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            dirs_to_check.append(meipass)
    else:
        dirs_to_check.append(os.path.dirname(os.path.abspath(__file__)))
        dirs_to_check.append(os.path.dirname(os.path.abspath(sys.executable)))

    dirs_to_check.append(os.getcwd())

    unique_dirs = []
    for d in dirs_to_check:
        if d and d not in unique_dirs:
            unique_dirs.append(d)

    for exe_dir in unique_dirs:
        p1 = os.path.join(exe_dir, "Tesseract-OCR", "tesseract.exe")
        p2 = os.path.join(exe_dir, "tesseract.exe")
        checked.append(p1)
        if os.path.isfile(p1):
            return p1, checked
        checked.append(p2)
        if os.path.isfile(p2):
            return p2, checked

    # 3. User local appdata (%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        p_local = os.path.join(local_appdata, "Programs", "Tesseract-OCR", "tesseract.exe")
        checked.append(p_local)
        if os.path.isfile(p_local):
            return p_local, checked
    else:
        home_local = os.path.expanduser("~\\AppData\\Local\\Programs\\Tesseract-OCR\\tesseract.exe")
        checked.append(home_local)
        if os.path.isfile(home_local):
            return home_local, checked

    # 4. System installation paths
    sys_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p_sys in sys_paths:
        checked.append(p_sys)
        if os.path.isfile(p_sys):
            return p_sys, checked

    # 5. Check PATH via shutil.which
    which_path = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if which_path:
        checked.append(f"PATH ({which_path})")
        if os.path.isfile(which_path):
            return which_path, checked

    return None, checked


def scan_pdf_text(pdf_path):
    if not os.path.exists(pdf_path):
        return {"error": f"PDF file not found: {pdf_path}"}

    doc = fitz.open(pdf_path)
    pages = []
    full_text = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        pages.append({"page": page_num + 1, "text": text})
        full_text.append(text)
    doc.close()

    combined = "\n".join(full_text)
    return {
        "pages": len(pages),
        "char_count": len(combined),
        "sample": combined[:4000],
        "pages_detail": pages,
    }


def scan_pdf_text_ocr(pdf_path):
    if not OCR_AVAILABLE or pytesseract is None:
        return {
            "error": "OCR unavailable. Install pytesseract, Pillow, and Tesseract OCR.",
            "install_hint": "pip install pytesseract Pillow && install Tesseract OCR from https://github.com/tesseract-ocr/tesseract",
        }
    
    tesseract_path, checked_locations = get_tesseract_cmd()
    if not tesseract_path:
        locations_fmt = "\n".join(f" - {loc}" for loc in checked_locations)
        return {
            "error": f"OCR unavailable. Tesseract binary not found across checked locations:\n{locations_fmt}",
            "install_hint": "Place a portable 'Tesseract-OCR' folder containing 'tesseract.exe' next to PDFTextReplacer.exe (no admin rights needed!), or set TESSERACT_CMD environment variable.",
            "checked_locations": checked_locations,
        }

    pytesseract.pytesseract.tesseract_cmd = tesseract_path

    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        return {
            "error": f"OCR unavailable. Failed to execute Tesseract binary at '{tesseract_path}': {e}",
            "install_hint": "Ensure Tesseract OCR installation is valid and binary is executable.",
        }

    doc = fitz.open(pdf_path)
    pages = []
    full_text = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        text = pytesseract.image_to_string(img)
        pages.append({"page": page_num + 1, "text": text})
        full_text.append(text)
    doc.close()

    combined = "\n".join(full_text)
    return {
        "pages": len(pages),
        "char_count": len(combined),
        "sample": combined[:4000],
        "pages_detail": pages,
        "mode": "ocr",
    }


def replace_text_in_pdf(pdf_path, search_text, replace_text, output_path=None):
    if not os.path.exists(pdf_path):
        print(f'Error: PDF file not found: {pdf_path}')
        sys.exit(1)
    if not search_text:
        print('Error: search_text cannot be empty')
        sys.exit(1)
    if replace_text is None:
        print('Error: replace_text cannot be None')
        sys.exit(1)
    if output_path is None:
        base, ext = os.path.splitext(pdf_path)
        base_name = os.path.basename(base)
        # Strip any leading timestamps and trailing _edited suffixes to prevent chaining on successive edits
        base_name = re.sub(r'^(\d{8}_\d{6}_)+', '', base_name)
        base_name = re.sub(r'(_edited(?:_\w+)*)+$', '', base_name)
        if len(base_name) > 100:
            base_name = base_name[:100]
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(os.path.dirname(pdf_path), f'{timestamp}_{base_name}_edited.pdf')
        if os.path.abspath(output_path) == os.path.abspath(pdf_path):
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_1')
            output_path = os.path.join(os.path.dirname(pdf_path), f'{timestamp}_{base_name}_edited.pdf')
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    else:
        os.makedirs('.', exist_ok=True)
    doc = fitz.open(pdf_path)
    found = False
    for page_num in range(len(doc)):
        if found:
            break
        page = doc[page_num]
        text_instances = page.search_for(search_text)
        if not text_instances:
            continue
        bbox = text_instances[0]

        # Detect original font properties BEFORE redaction
        font_size = 11
        font_name = None
        font_color = (0, 0, 0)
        try:
            for block in page.get_text('dict')['blocks']:
                if 'lines' not in block:
                    continue
                for line in block['lines']:
                    for span in line['spans']:
                        if search_text in span['text']:
                            font_size = span.get('size', font_size)
                            font_name = span.get('font', None)
                            color = span.get('color', None)
                            if color is not None:
                                if isinstance(color, int):
                                    # PyMuPDF may return packed RGB integer
                                    r = (color >> 16) & 0xFF
                                    g = (color >> 8) & 0xFF
                                    b = color & 0xFF
                                    font_color = (r / 255.0, g / 255.0, b / 255.0)
                                elif isinstance(color, (tuple, list)):
                                    font_color = tuple(c / 255.0 if c > 1 else c for c in color)
                            break
        except Exception:
            pass

        page.add_redact_annot(bbox, text='', fill=(1, 1, 1))
        page.apply_redactions()

        insert_kwargs = {
            'fontsize': font_size,
            'color': font_color,
        }
        if font_name:
            insert_kwargs['fontname'] = font_name

        try:
            page.insert_text(bbox.bl, replace_text, **insert_kwargs)
        except Exception:
            safe_kwargs = {
                'fontsize': font_size,
                'color': font_color,
                'fontname': 'helv',
            }
            try:
                page.insert_text(bbox.bl, replace_text, **safe_kwargs)
            except Exception:
                # Final fallback: keep text inside the original bounding box
                page.insert_textbox(
                    bbox,
                    replace_text,
                    fontsize=font_size,
                    color=font_color,
                    fontname='helv',
                    align=fitz.TEXT_ALIGN_LEFT,
                    vertical_align='top',
                )

        found = True
    if not found:
        print(f'Warning: {search_text!r} not found in PDF')
        doc.close()
        return None
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    print(f'Done. Saved to: {output_path}')
    return output_path

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage:')
        print('  python replace_pdf_text.py scan <pdf_path>')
        print('  python replace_pdf_text.py <pdf_path> <search_text> <replace_text> [output_path]')
        sys.exit(1)

    pdf_path = sys.argv[1]
    if sys.argv[2].lower() == 'scan':
        result = scan_pdf_text(pdf_path)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if 'error' not in result else 1)

    if len(sys.argv) < 4:
        print('Usage: python replace_pdf_text.py <pdf_path> <search_text> <replace_text> [output_path]')
        sys.exit(1)

    search_text = sys.argv[2]
    replace_text = sys.argv[3]
    output_path = sys.argv[4] if len(sys.argv) > 4 else None
    result = replace_text_in_pdf(pdf_path, search_text, replace_text, output_path)
    sys.exit(0 if result else 1)
