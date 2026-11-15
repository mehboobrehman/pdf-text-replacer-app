import os
import sys
import json
import io
import contextlib
import re
from datetime import datetime

import fitz
from PIL import Image

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    OCR_AVAILABLE = False


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
            "error": "OCR unavailable. Install pytesseract, Pillow.",
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
        return None
    if not search_text:
        print('Error: search_text cannot be empty')
        return None
    if replace_text is None:
        print('Error: replace_text cannot be None')
        return None

    if output_path is None:
        base, ext = os.path.splitext(pdf_path)
        base_name = os.path.basename(base)
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


def replace_text_bridge(pdf_path, search_text, replace_text):
    output_dir = os.path.join(os.path.dirname(os.path.dirname(pdf_path)), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    base_name = re.sub(r'^(\d{8}_\d{6}_)+', '', base_name)
    base_name = re.sub(r'(_edited(?:_\w+)*)+$', '', base_name)
    if len(base_name) > 100:
        base_name = base_name[:100]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_name = f"{timestamp}_{base_name}_edited.pdf"
    output_path = os.path.join(output_dir, output_name)

    stdout_io = io.StringIO()
    stderr_io = io.StringIO()
    returncode = 0
    res_path = None

    try:
        with contextlib.redirect_stdout(stdout_io), contextlib.redirect_stderr(stderr_io):
            res_path = replace_text_in_pdf(pdf_path, search_text, replace_text, output_path)
            if not res_path:
                returncode = 1
    except Exception as e:
        import traceback
        traceback.print_exc(file=stderr_io)
        returncode = 1

    return {
        "stdout": stdout_io.getvalue(),
        "stderr": stderr_io.getvalue(),
        "returncode": returncode,
        "output": output_path if returncode == 0 else None,
        "output_name": output_name if returncode == 0 else None,
    }


def preview_pdf_bridge(pdf_path, mode="text"):
    if mode.strip().lower() == "ocr":
        return scan_pdf_text_ocr(pdf_path)
    return scan_pdf_text(pdf_path)
