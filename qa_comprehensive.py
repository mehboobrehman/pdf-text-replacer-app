#!/usr/bin/env python3
"""Comprehensive QA test for pdf-text-replacer-app using Playwright."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
PROJECT_ROOT = Path(__file__).parent
QA_TESTS_DIR = PROJECT_ROOT / "qa_tests"
UPLOAD_DIR = PROJECT_ROOT / "uploaded"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Test files available
TEST_FILES = {
    "basic": QA_TESTS_DIR / "test_basic.pdf",
    "unicode": QA_TESTS_DIR / "test_unicode.pdf",
    "special": QA_TESTS_DIR / "test_special.pdf",
    "empty": QA_TESTS_DIR / "test_empty.pdf",
    "scanned": QA_TESTS_DIR / "test_scanned.pdf",
    "fake": QA_TESTS_DIR / "fake.pdf",
    "large": QA_TESTS_DIR / "test_large.pdf",
    "true_scanned": QA_TESTS_DIR / "test_true_scanned.pdf",
}

# Track all issues found
issues = []

def add_issue(severity, category, title, description, steps_to_reproduce, expected, actual):
    """Add an issue to the tracking list."""
    issues.append({
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "steps_to_reproduce": steps_to_reproduce,
        "expected": expected,
        "actual": actual
    })

async def test_api_endpoints(page):
    """Test backend API endpoints directly."""
    print("\n=== Testing API Endpoints ===")
    results = {}
    
    # Test /api/health
    try:
        response = await page.request.get(f"{BASE_URL}/api/health")
        data = await response.json()
        assert response.ok, f"Health check failed: {response.status}"
        assert data["status"] == "ok"
        print("✓ /api/health - PASS")
        results["health"] = "PASS"
    except Exception as e:
        print(f"✗ /api/health - FAIL: {e}")
        results["health"] = f"FAIL: {e}"
        add_issue("critical", "API", "Health endpoint fails", "Health endpoint returns error", 
                  "GET /api/health", "200 OK with status=ok", str(e))
    
    # Test /api/upload with a valid PDF
    upload_path = None
    try:
        test_file = TEST_FILES["basic"]
        if test_file.exists():
            with open(test_file, "rb") as f:
                form_data = {
                    "file": (test_file.name, f.read(), "application/pdf")
                }
                response = await page.request.post(f"{BASE_URL}/api/upload", multipart=form_data)
                data = await response.json()
                assert response.ok, f"Upload failed: {response.status} - {data}"
                assert "path" in data
                assert "filename" in data
                print(f"✓ /api/upload - PASS (uploaded: {data['filename']})")
                results["upload"] = "PASS"
                upload_path = data["path"]
        else:
            print("⚠ /api/upload - SKIP: test_basic.pdf not found")
            results["upload"] = "SKIP"
    except Exception as e:
        print(f"✗ /api/upload - FAIL: {e}")
        results["upload"] = f"FAIL: {e}"
        add_issue("high", "API", "Upload endpoint fails with Playwright multipart", 
                  "Playwright's multipart form data doesn't send file content correctly",
                  "POST /api/upload with multipart form data containing PDF file",
                  "200 OK with path and filename", f"400 Bad Request: {e}")
    
    # Test /api/preview with text mode
    if upload_path:
        try:
            response = await page.request.post(f"{BASE_URL}/api/preview", 
                data=json.dumps({"pdf_path": upload_path, "mode": "text"}),
                headers={"Content-Type": "application/json"})
            data = await response.json()
            assert response.ok, f"Preview failed: {response.status}"
            assert "pages" in data
            assert "sample" in data
            print(f"✓ /api/preview (text) - PASS ({data['pages']} pages, {data['char_count']} chars)")
            results["preview_text"] = "PASS"
        except Exception as e:
            print(f"✗ /api/preview (text) - FAIL: {e}")
            results["preview_text"] = f"FAIL: {e}"
            add_issue("high", "API", "Text preview endpoint fails", "Preview endpoint returns error",
                      f"POST /api/preview with pdf_path={upload_path}, mode=text",
                      "200 OK with pages, char_count, sample", str(e))
    
    # Test /api/preview with OCR mode
    if upload_path:
        try:
            response = await page.request.post(f"{BASE_URL}/api/preview",
                data=json.dumps({"pdf_path": upload_path, "mode": "ocr"}),
                headers={"Content-Type": "application/json"})
            data = await response.json()
            if response.ok:
                print(f"✓ /api/preview (ocr) - PASS ({data.get('pages', '?')} pages)")
                results["preview_ocr"] = "PASS"
            else:
                if "OCR unavailable" in str(data.get("error", "")):
                    print(f"⚠ /api/preview (ocr) - SKIP: OCR not available")
                    results["preview_ocr"] = "SKIP"
                else:
                    print(f"✗ /api/preview (ocr) - FAIL: {data}")
                    results["preview_ocr"] = f"FAIL: {data}"
                    add_issue("medium", "API", "OCR preview endpoint fails unexpectedly", 
                              "OCR preview returns error other than 'OCR unavailable'",
                              f"POST /api/preview with pdf_path={upload_path}, mode=ocr",
                              "200 OK with OCR results or 500 with 'OCR unavailable'", str(data))
        except Exception as e:
            print(f"✗ /api/preview (ocr) - FAIL: {e}")
            results["preview_ocr"] = f"FAIL: {e}"
    
    # Test /api/replace with valid data (using text that exists in PDF)
    replace_output = None
    if upload_path:
        try:
            response = await page.request.post(f"{BASE_URL}/api/replace",
                data=json.dumps({
                    "pdf_path": upload_path,
                    "search_text": "Hello",
                    "replace_text": "REPLACED"
                }),
                headers={"Content-Type": "application/json"})
            data = await response.json()
            assert response.ok, f"Replace failed: {response.status}"
            if data.get("returncode") == 0:
                print(f"✓ /api/replace - PASS (output: {data.get('output_name')})")
                results["replace"] = "PASS"
                replace_output = data.get("output_name")
            else:
                print(f"⚠ /api/replace - PARTIAL: returncode={data.get('returncode')}, stderr={data.get('stderr')}")
                results["replace"] = f"PARTIAL: {data.get('stderr')}"
        except Exception as e:
            print(f"✗ /api/replace - FAIL: {e}")
            results["replace"] = f"FAIL: {e}"
            add_issue("high", "API", "Replace endpoint fails", "Replace endpoint returns error",
                      f"POST /api/replace with valid pdf_path, search_text, replace_text",
                      "200 OK with returncode=0 and output_name", str(e))
    
    # Test /api/replace with missing search_text (should fail)
    if upload_path:
        try:
            response = await page.request.post(f"{BASE_URL}/api/replace",
                data=json.dumps({
                    "pdf_path": upload_path,
                    "search_text": "",
                    "replace_text": "Replaced"
                }),
                headers={"Content-Type": "application/json"})
            data = await response.json()
            assert not response.ok or data.get("returncode") != 0, "Should fail with empty search_text"
            print(f"✓ /api/replace (empty search) - PASS (correctly rejected)")
            results["replace_empty_search"] = "PASS"
        except Exception as e:
            print(f"✗ /api/replace (empty search) - FAIL: {e}")
            results["replace_empty_search"] = f"FAIL: {e}"
    
    # Test /api/replace with non-existent search text
    if upload_path:
        try:
            response = await page.request.post(f"{BASE_URL}/api/replace",
                data=json.dumps({
                    "pdf_path": upload_path,
                    "search_text": "ThisTextDoesNotExistInThePDF",
                    "replace_text": "Replaced"
                }),
                headers={"Content-Type": "application/json"})
            data = await response.json()
            if data.get("returncode") != 0:
                print(f"✓ /api/replace (text not found) - PASS (correctly reported not found)")
                results["replace_not_found"] = "PASS"
            else:
                print(f"⚠ /api/replace (text not found) - PARTIAL: returned success but text wasn't found")
                results["replace_not_found"] = "PARTIAL"
                add_issue("medium", "API", "Replace succeeds when text not found", 
                          "Replace endpoint returns success even when search text doesn't exist in PDF",
                          f"POST /api/replace with non-existent search_text",
                          "returncode != 0 with warning about text not found", "returncode=0 (success)")
        except Exception as e:
            print(f"✗ /api/replace (text not found) - FAIL: {e}")
            results["replace_not_found"] = f"FAIL: {e}"
    
    # Test /output/ endpoint for downloading
    if replace_output:
        try:
            response = await page.request.get(f"{BASE_URL}/output/{replace_output}")
            assert response.ok, f"Download failed: {response.status}"
            content = await response.body()
            assert len(content) > 0, "Downloaded file is empty"
            assert content[:4] == b"%PDF", "Downloaded file is not a valid PDF"
            print(f"✓ /output/ download - PASS ({len(content)} bytes)")
            results["download"] = "PASS"
        except Exception as e:
            print(f"✗ /output/ download - FAIL: {e}")
            results["download"] = f"FAIL: {e}"
            add_issue("high", "API", "Download endpoint fails", "Cannot download processed PDF",
                      f"GET /output/{replace_output}", "200 OK with valid PDF content", str(e))
    
    # Test static file serving
    try:
        response = await page.request.get(f"{BASE_URL}/")
        assert response.ok, f"Index failed: {response.status}"
        content = await response.text()
        assert "PDF Text Replacer" in content
        print(f"✓ Static file serving (index.html) - PASS")
        results["static_index"] = "PASS"
    except Exception as e:
        print(f"✗ Static file serving (index.html) - FAIL: {e}")
        results["static_index"] = f"FAIL: {e}"
    
    try:
        response = await page.request.get(f"{BASE_URL}/styles.css")
        assert response.ok, f"CSS failed: {response.status}"
        print(f"✓ Static file serving (styles.css) - PASS")
        results["static_css"] = "PASS"
    except Exception as e:
        print(f"✗ Static file serving (styles.css) - FAIL: {e}")
        results["static_css"] = f"FAIL: {e}"
    
    try:
        response = await page.request.get(f"{BASE_URL}/app.js")
        assert response.ok, f"JS failed: {response.status}"
        print(f"✓ Static file serving (app.js) - PASS")
        results["static_js"] = "PASS"
    except Exception as e:
        print(f"✗ Static file serving (app.js) - FAIL: {e}")
        results["static_js"] = f"FAIL: {e}"
    
    return results


async def test_ui_workflow(page):
    """Test the complete UI workflow."""
    print("\n=== Testing UI Workflow ===")
    results = {}
    
    # Navigate to the app
    try:
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_load_state("domcontentloaded")
        
        # Verify page loaded
        await page.wait_for_selector("#dropZone", timeout=5000)
        print("✓ Page loaded - PASS")
        results["page_load"] = "PASS"
    except Exception as e:
        print(f"✗ Page load - FAIL: {e}")
        results["page_load"] = f"FAIL: {e}"
        add_issue("critical", "UI", "Page fails to load", "Main page doesn't load or dropZone not found",
                  "Navigate to http://127.0.0.1:5173/", "Page loads with dropZone visible", str(e))
        return results
    
    # Test drag-and-drop visual feedback
    try:
        drop_zone = await page.query_selector("#dropZone")
        # Simulate drag enter
        await drop_zone.evaluate("el => el.classList.add('drag-over')")
        await page.wait_for_timeout(100)
        has_class = await drop_zone.evaluate("el => el.classList.contains('drag-over')")
        await drop_zone.evaluate("el => el.classList.remove('drag-over')")
        
        if has_class:
            print("✓ Drag-over visual feedback - PASS")
            results["drag_over_feedback"] = "PASS"
        else:
            print("✗ Drag-over visual feedback - FAIL")
            results["drag_over_feedback"] = "FAIL"
            add_issue("low", "UI", "Drag-over visual feedback not working", 
                      "dropZone doesn't get drag-over class on dragover",
                      "Drag file over dropZone", "dropZone gets drag-over class (blue border, light blue bg)", "Class not added")
    except Exception as e:
        print(f"✗ Drag-over visual feedback - FAIL: {e}")
        results["drag_over_feedback"] = f"FAIL: {e}"
    
    # Test file upload via file input (simulating drag-drop)
    try:
        test_file = TEST_FILES["basic"]
        if test_file.exists():
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            
            # Wait for editor section to appear
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            # Verify file info is displayed
            file_name = await page.text_content("#fileName")
            file_size = await page.text_content("#fileSize")
            file_path = await page.text_content("#filePath")
            
            assert "test_basic" in file_name.lower(), f"Filename not displayed correctly: {file_name}"
            assert file_size != "-", f"File size not displayed: {file_size}"
            assert file_path != "-", f"File path not displayed: {file_path}"
            
            print(f"✓ File upload - PASS (name: {file_name}, size: {file_size})")
            results["file_upload"] = "PASS"
        else:
            print("⚠ File upload - SKIP: test_basic.pdf not found")
            results["file_upload"] = "SKIP"
    except Exception as e:
        print(f"✗ File upload - FAIL: {e}")
        results["file_upload"] = f"FAIL: {e}"
        add_issue("high", "UI", "File upload fails", "Uploaded file doesn't show editor section or file info",
                  "Select PDF file via file input", "Editor section visible with file name, size, path", str(e))
    
    # Test Preview button (text mode)
    try:
        await page.click("#previewButton")
        await page.wait_for_selector("#previewSection:not(.hidden)", timeout=10000)
        
        preview_meta = await page.text_content("#previewMeta")
        preview_body = await page.text_content("#previewBody")
        
        assert "pages" in preview_meta.lower(), f"Preview meta not correct: {preview_meta}"
        assert preview_body and len(preview_body) > 0, "Preview body is empty"
        
        print(f"✓ Preview (text) - PASS (meta: {preview_meta})")
        results["preview_text_ui"] = "PASS"
    except Exception as e:
        print(f"✗ Preview (text) - FAIL: {e}")
        results["preview_text_ui"] = f"FAIL: {e}"
        add_issue("high", "UI", "Text preview fails", "Preview section doesn't show or content empty",
                  "Click Preview button with PDF loaded", "Preview section visible with page count and text sample", str(e))
    
    # Test OCR toggle - click the label/toggle-track since checkbox is hidden
    try:
        # The checkbox has display: none, so we click the label or toggle-track
        ocr_label = await page.query_selector("label.toggle")
        await ocr_label.click()
        await page.wait_for_timeout(200)
        
        # Verify checkbox is checked
        is_checked = await page.is_checked("#ocrMode")
        if is_checked:
            print("✓ OCR toggle (click label) - PASS")
            results["ocr_toggle"] = "PASS"
        else:
            print("✗ OCR toggle (click label) - FAIL: checkbox not checked")
            results["ocr_toggle"] = "FAIL"
            add_issue("medium", "UI", "OCR checkbox not toggleable via label click", 
                      "Checkbox has display:none, clicking label doesn't toggle it",
                      "Click OCR mode label", "Checkbox gets checked", "Checkbox remains unchecked")
        
        # Uncheck for subsequent tests
        await ocr_label.click()
        await page.wait_for_timeout(200)
    except Exception as e:
        print(f"✗ OCR toggle - FAIL: {e}")
        results["ocr_toggle"] = f"FAIL: {e}"
        add_issue("medium", "UI", "OCR toggle interaction fails", "Cannot toggle OCR mode via UI",
                  "Click OCR mode label", "Checkbox toggles", str(e))
    
    # Test text replacement
    try:
        await page.fill("#searchText", "Hello")
        await page.fill("#replaceText", "REPLACED")
        await page.click("#replaceButton")
        
        # Wait for success status
        await page.wait_for_function(
            "() => document.getElementById('status').classList.contains('success')",
            timeout=30000
        )
        
        status_text = await page.text_content("#status")
        save_disabled = await page.get_attribute("#saveButton", "disabled")
        
        print(f"✓ Text replacement - PASS (status: {status_text}, save enabled: {save_disabled is None})")
        results["text_replace"] = "PASS"
    except Exception as e:
        print(f"✗ Text replacement - FAIL: {e}")
        results["text_replace"] = f"FAIL: {e}"
        add_issue("critical", "UI", "Text replacement times out or fails", 
                  "Replace operation doesn't complete or success status not shown",
                  "Fill search/replace fields, click Replace", "Success status shown, Save button enabled", str(e))
    
    # Test Save/Download button
    try:
        download_started = False
        
        async with page.expect_download() as download_info:
            await page.click("#saveButton")
            download = await download_info.value
        
        if download:
            download_path = await download.path()
            if download_path and os.path.getsize(download_path) > 0:
                print(f"✓ Save/Download - PASS (downloaded: {download.suggested_filename})")
                results["save_download"] = "PASS"
            else:
                print(f"⚠ Save/Download - PARTIAL (download initiated but file empty)")
                results["save_download"] = "PARTIAL"
                add_issue("medium", "UI", "Download produces empty file", 
                          "Save button triggers download but file is empty",
                          "Click Save after successful replace", "Valid PDF downloaded", "Empty file downloaded")
        else:
            print(f"⚠ Save/Download - PARTIAL (no download event)")
            results["save_download"] = "PARTIAL"
    except Exception as e:
        print(f"✗ Save/Download - FAIL: {e}")
        results["save_download"] = f"FAIL: {e}"
        add_issue("high", "UI", "Save/Download fails", "Save button doesn't trigger download",
                  "Click Save button after replace", "File downloaded via showSaveFilePicker or fallback", str(e))
    
    # Test New File button
    try:
        await page.click("#newFileButton")
        await page.wait_for_selector("#uploadSection:not(.hidden)", timeout=3000)
        assert await page.is_visible("#dropZone")
        assert await page.is_hidden("#editorSection")
        print("✓ New File button - PASS")
        results["new_file"] = "PASS"
    except Exception as e:
        print(f"✗ New File button - FAIL: {e}")
        results["new_file"] = f"FAIL: {e}"
        add_issue("medium", "UI", "New File button fails", "New File doesn't reset UI to upload state",
                  "Click New File button", "Upload section visible, editor section hidden", str(e))
    
    return results


async def test_edge_cases(page):
    """Test edge cases and error handling."""
    print("\n=== Testing Edge Cases ===")
    results = {}
    
    # Test with empty PDF
    try:
        test_file = TEST_FILES["empty"]
        if test_file.exists():
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            # Try preview
            await page.click("#previewButton")
            await page.wait_for_selector("#previewSection:not(.hidden)", timeout=5000)
            preview_body = await page.text_content("#previewBody")
            
            print(f"✓ Empty PDF handling - PASS (preview: {preview_body[:50]})")
            results["empty_pdf"] = "PASS"
        else:
            print("⚠ Empty PDF - SKIP: test_empty.pdf not found")
            results["empty_pdf"] = "SKIP"
    except Exception as e:
        print(f"✗ Empty PDF - FAIL: {e}")
        results["empty_pdf"] = f"FAIL: {e}"
        add_issue("medium", "Edge Case", "Empty PDF handling fails", "App crashes or errors on empty PDF",
                  "Upload empty PDF, click Preview", "Preview shows '(no extractable text)' or similar", str(e))
    
    # Test with special characters PDF
    try:
        test_file = TEST_FILES["special"]
        if test_file.exists():
            await page.click("#newFileButton")
            await page.wait_for_selector("#uploadSection:not(.hidden)", timeout=3000)
            
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            await page.click("#previewButton")
            await page.wait_for_selector("#previewSection:not(.hidden)", timeout=5000)
            preview_body = await page.text_content("#previewBody")
            
            print(f"✓ Special chars PDF - PASS (preview length: {len(preview_body)})")
            results["special_chars"] = "PASS"
        else:
            print("⚠ Special chars PDF - SKIP: test_special.pdf not found")
            results["special_chars"] = "SKIP"
    except Exception as e:
        print(f"✗ Special chars PDF - FAIL: {e}")
        results["special_chars"] = f"FAIL: {e}"
        add_issue("medium", "Edge Case", "Special characters PDF fails", "App doesn't handle special characters correctly",
                  "Upload special chars PDF, click Preview", "Preview shows special characters correctly", str(e))
    
    # Test with unicode PDF
    try:
        test_file = TEST_FILES["unicode"]
        if test_file.exists():
            await page.click("#newFileButton")
            await page.wait_for_selector("#uploadSection:not(.hidden)", timeout=3000)
            
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            await page.click("#previewButton")
            await page.wait_for_selector("#previewSection:not(.hidden)", timeout=5000)
            preview_body = await page.text_content("#previewBody")
            
            print(f"✓ Unicode PDF - PASS (preview length: {len(preview_body)})")
            results["unicode_pdf"] = "PASS"
        else:
            print("⚠ Unicode PDF - SKIP: test_unicode.pdf not found")
            results["unicode_pdf"] = "SKIP"
    except Exception as e:
        print(f"✗ Unicode PDF - FAIL: {e}")
        results["unicode_pdf"] = f"FAIL: {e}"
        add_issue("medium", "Edge Case", "Unicode PDF fails", "App doesn't handle unicode characters correctly",
                  "Upload unicode PDF, click Preview", "Preview shows unicode characters correctly", str(e))
    
    # Test with scanned PDF (OCR) - only if Tesseract available
    try:
        test_file = TEST_FILES["scanned"]
        if test_file.exists():
            await page.click("#newFileButton")
            await page.wait_for_selector("#uploadSection:not(.hidden)", timeout=3000)
            
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            # Test with OCR mode - click label to toggle
            ocr_label = await page.query_selector("label.toggle")
            await ocr_label.click()
            await page.wait_for_timeout(200)
            
            await page.click("#previewButton")
            await page.wait_for_selector("#previewSection:not(.hidden)", timeout=30000)
            preview_body = await page.text_content("#previewBody")
            
            # Uncheck OCR
            await ocr_label.click()
            await page.wait_for_timeout(200)
            
            # Check if OCR actually worked or returned error
            if "OCR unavailable" in preview_body or "unavailable" in preview_body.lower():
                print(f"⚠ Scanned PDF (OCR) - SKIP: OCR not available")
                results["scanned_pdf_ocr"] = "SKIP"
            else:
                print(f"✓ Scanned PDF (OCR) - PASS (preview length: {len(preview_body)})")
                results["scanned_pdf_ocr"] = "PASS"
        else:
            print("⚠ Scanned PDF - SKIP: test_scanned.pdf not found")
            results["scanned_pdf_ocr"] = "SKIP"
    except Exception as e:
        print(f"✗ Scanned PDF (OCR) - FAIL: {e}")
        results["scanned_pdf_ocr"] = f"FAIL: {e}"
        add_issue("medium", "Edge Case", "Scanned PDF OCR fails", "OCR preview doesn't work for scanned PDF",
                  "Upload scanned PDF, enable OCR, click Preview", "OCR extracts text from images", str(e))
    
    # Test invalid file upload (non-PDF)
    try:
        # Create a fake text file
        fake_file = PROJECT_ROOT / "fake.txt"
        with open(fake_file, "w") as f:
            f.write("This is not a PDF")
        
        file_input = await page.query_selector("#fileInput")
        await file_input.set_input_files(str(fake_file))
        
        # Should show error status
        await page.wait_for_function(
            "() => document.getElementById('status').classList.contains('error')",
            timeout=5000
        )
        status_text = await page.text_content("#status")
        
        fake_file.unlink()
        print(f"✓ Invalid file rejection - PASS (status: {status_text})")
        results["invalid_file"] = "PASS"
    except Exception as e:
        print(f"✗ Invalid file rejection - FAIL: {e}")
        results["invalid_file"] = f"FAIL: {e}"
        add_issue("high", "Edge Case", "Invalid file not rejected properly", "Non-PDF files not rejected with error message",
                  "Upload .txt file via file input", "Error status shown: 'Please select a PDF file.'", str(e))
    
    # Test empty search text validation
    try:
        await page.click("#newFileButton")
        await page.wait_for_selector("#uploadSection:not(.hidden)", timeout=3000)
        
        test_file = TEST_FILES["basic"]
        if test_file.exists():
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            # Try replace with empty search
            await page.fill("#searchText", "")
            await page.fill("#replaceText", "Something")
            await page.click("#replaceButton")
            
            await page.wait_for_function(
                "() => document.getElementById('status').classList.contains('error')",
                timeout=5000
            )
            status_text = await page.text_content("#status")
            
            print(f"✓ Empty search validation - PASS (status: {status_text})")
            results["empty_search_validation"] = "PASS"
        else:
            print("⚠ Empty search validation - SKIP: test_basic.pdf not found")
            results["empty_search_validation"] = "SKIP"
    except Exception as e:
        print(f"✗ Empty search validation - FAIL: {e}")
        results["empty_search_validation"] = f"FAIL: {e}"
        add_issue("medium", "Edge Case", "Empty search validation fails", "Empty search text not validated",
                  "Click Replace with empty search field", "Error status: 'Enter search text.'", str(e))
    
    # Test empty replace text validation
    try:
        await page.fill("#searchText", "Hello")
        await page.fill("#replaceText", "")
        await page.click("#replaceButton")
        
        await page.wait_for_function(
            "() => document.getElementById('status').classList.contains('error')",
            timeout=5000
        )
        status_text = await page.text_content("#status")
        
        print(f"✓ Empty replace validation - PASS (status: {status_text})")
        results["empty_replace_validation"] = "PASS"
    except Exception as e:
        print(f"✗ Empty replace validation - FAIL: {e}")
        results["empty_replace_validation"] = f"FAIL: {e}"
        add_issue("medium", "Edge Case", "Empty replace validation fails", "Empty replace text not validated",
                  "Click Replace with empty replace field", "Error status: 'Enter replacement text.'", str(e))
    
    # Test case sensitivity
    try:
        await page.click("#newFileButton")
        await page.wait_for_selector("#uploadSection:not(.hidden)", timeout=3000)
        
        test_file = TEST_FILES["basic"]
        if test_file.exists():
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            # Search for "hello" (lowercase) - should not match "Hello"
            await page.fill("#searchText", "hello")
            await page.fill("#replaceText", "REPLACED_LOWER")
            await page.click("#replaceButton")
            
            await page.wait_for_function(
                "() => document.getElementById('status').classList.contains('error')",
                timeout=15000
            )
            status_text = await page.text_content("#status")
            
            # Should fail because "hello" != "Hello" (case sensitive)
            if "not found" in status_text.lower() or "warning" in status_text.lower():
                print(f"✓ Case sensitivity - PASS (correctly case sensitive: {status_text})")
                results["case_sensitivity"] = "PASS"
            else:
                print(f"⚠ Case sensitivity - PARTIAL (may not be case sensitive: {status_text})")
                results["case_sensitivity"] = "PARTIAL"
                add_issue("low", "Edge Case", "Case sensitivity unclear", "Search may not be case sensitive as expected",
                          "Search for 'hello' (lowercase) in PDF with 'Hello'", "Text not found error (case sensitive)", status_text)
        else:
            print("⚠ Case sensitivity - SKIP: test_basic.pdf not found")
            results["case_sensitivity"] = "SKIP"
    except Exception as e:
        print(f"✗ Case sensitivity - FAIL: {e}")
        results["case_sensitivity"] = f"FAIL: {e}"
    
    return results


async def test_output_verification(page):
    """Verify the output PDF actually has replaced text correctly."""
    print("\n=== Verifying Output PDF Content ===")
    results = {}
    
    try:
        # Upload a test file
        test_file = TEST_FILES["basic"]
        if test_file.exists():
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            # Preview first to see original text
            await page.click("#previewButton")
            await page.wait_for_selector("#previewSection:not(.hidden)", timeout=5000)
            original_preview = await page.text_content("#previewBody")
            print(f"  Original preview sample: {original_preview[:100]}...")
            
            # Count occurrences of "Hello" in original
            import fitz
            doc = fitz.open(str(test_file))
            original_full_text = ""
            for p in doc:
                original_full_text += p.get_text("text")
            doc.close()
            hello_count = original_full_text.count("Hello")
            print(f"  Original 'Hello' count: {hello_count}")
            
            # Perform replacement
            await page.fill("#searchText", "Hello")
            await page.fill("#replaceText", "REPLACED_SUCCESSFULLY")
            await page.click("#replaceButton")
            
            await page.wait_for_function(
                "() => document.getElementById('status').classList.contains('success')",
                timeout=30000
            )
            
            # Download the result
            async with page.expect_download() as download_info:
                await page.click("#saveButton")
            download = await download_info.value
            
            if download:
                download_path = await download.path()
                if download_path and os.path.getsize(download_path) > 0:
                    # Verify the PDF content using PyMuPDF
                    doc = fitz.open(download_path)
                    full_text = ""
                    for page_num in range(len(doc)):
                        full_text += doc[page_num].get_text("text")
                    doc.close()
                    
                    replaced_count = full_text.count("REPLACED_SUCCESSFULLY")
                    remaining_hello = full_text.count("Hello")
                    
                    print(f"  Output 'REPLACED_SUCCESSFULLY' count: {replaced_count}")
                    print(f"  Output remaining 'Hello' count: {remaining_hello}")
                    
                    if replaced_count == hello_count and remaining_hello == 0:
                        print(f"✓ Output PDF verification - PASS (all {hello_count} occurrences replaced)")
                        results["output_verification"] = "PASS"
                    elif replaced_count > 0 and remaining_hello > 0:
                        print(f"⚠ Output PDF verification - PARTIAL ({replaced_count}/{hello_count} replaced, {remaining_hello} remain)")
                        results["output_verification"] = "PARTIAL"
                        add_issue("critical", "Core Functionality", "Text replacement only replaces first occurrence", 
                                  f"Only the first occurrence of search text is replaced. Expected {hello_count} replacements, got {replaced_count}. {remaining_hello} occurrences remain.",
                                  "Upload PDF with multiple 'Hello' occurrences, search for 'Hello', replace with 'REPLACED'",
                                  f"All {hello_count} occurrences of 'Hello' replaced", 
                                  f"Only {replaced_count} occurrence(s) replaced, {remaining_hello} remain")
                    elif replaced_count > 0:
                        print(f"⚠ Output PDF verification - PARTIAL (replaced text found but original may still exist)")
                        results["output_verification"] = "PARTIAL"
                    else:
                        print(f"✗ Output PDF verification - FAIL (replaced text not found in output)")
                        print(f"  Output text sample: {full_text[:200]}")
                        results["output_verification"] = "FAIL"
                        add_issue("critical", "Core Functionality", "Text replacement produces no changes", 
                                  "Replacement completes successfully but output PDF has no replaced text",
                                  "Upload PDF, search for existing text, replace, download output",
                                  "Output PDF contains replaced text", "Output PDF unchanged")
                else:
                    print(f"✗ Output PDF verification - FAIL (download empty)")
                    results["output_verification"] = "FAIL"
            else:
                print(f"✗ Output PDF verification - FAIL (no download)")
                results["output_verification"] = "FAIL"
        else:
            print("⚠ Output verification - SKIP: test_basic.pdf not found")
            results["output_verification"] = "SKIP"
    except Exception as e:
        print(f"✗ Output PDF verification - FAIL: {e}")
        results["output_verification"] = f"FAIL: {e}"
        add_issue("critical", "Core Functionality", "Output verification fails", "Cannot verify output PDF content",
                  "Upload PDF, replace text, download and verify", "Output PDF verified with replaced text", str(e))
    
    return results


async def test_replacement_multiple_occurrences_directly():
    """Test the replace_pdf_text.py script directly to verify multiple occurrence bug."""
    print("\n=== Testing Replacement Script Directly ===")
    results = {}
    
    try:
        import subprocess
        import sys
        
        script_path = PROJECT_ROOT / "scripts" / "replace_pdf_text.py"
        test_pdf = TEST_FILES["basic"]
        output_pdf = OUTPUT_DIR / "direct_test_output.pdf"
        
        cmd = [
            sys.executable,
            str(script_path),
            str(test_pdf),
            "Hello",
            "DIRECT_REPLACED",
            str(output_pdf)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        print(f"  Return code: {result.returncode}")
        print(f"  Stdout: {result.stdout}")
        print(f"  Stderr: {result.stderr}")
        
        if result.returncode == 0:
            import fitz
            doc = fitz.open(str(output_pdf))
            full_text = ""
            for p in doc:
                full_text += p.get_text("text")
            doc.close()
            
            replaced_count = full_text.count("DIRECT_REPLACED")
            remaining_hello = full_text.count("Hello")
            
            print(f"  Direct test - Replaced: {replaced_count}, Remaining Hello: {remaining_hello}")
            
            if replaced_count == 1 and remaining_hello > 0:
                print(f"  ✗ Multiple occurrence bug CONFIRMED: Only 1 occurrence replaced")
                results["multiple_occurrences"] = "FAIL - Only first occurrence replaced"
                add_issue("critical", "Core Functionality", "replace_pdf_text.py only replaces first occurrence",
                          "The replace_text_in_pdf function breaks after finding the first match on the first page",
                          "Run replace_pdf_text.py with search text that appears multiple times",
                          "All occurrences replaced", "Only first occurrence replaced")
            elif replaced_count > 1:
                print(f"  ✓ Multiple occurrences replaced: {replaced_count}")
                results["multiple_occurrences"] = f"PASS - {replaced_count} occurrences replaced"
            else:
                print(f"  ✗ No replacements made")
                results["multiple_occurrences"] = "FAIL - No replacements"
        else:
            print(f"  ✗ Script failed: {result.stderr}")
            results["multiple_occurrences"] = f"FAIL: {result.stderr}"
            
    except Exception as e:
        print(f"  ✗ Direct test error: {e}")
        results["multiple_occurrences"] = f"FAIL: {e}"
    
    return results


async def check_console_errors(page):
    """Check for JavaScript console errors."""
    print("\n=== Checking Console Errors ===")
    console_errors = []
    
    def handle_console(msg):
        if msg.type == "error":
            console_errors.append(msg.text)
    
    page.on("console", handle_console)
    
    # Reload page to catch any initialization errors
    await page.reload(wait_until="networkidle")
    await page.wait_for_timeout(1000)
    
    if console_errors:
        print(f"⚠ Console errors found ({len(console_errors)}):")
        for err in console_errors:
            print(f"  - {err}")
        add_issue("medium", "UI", "JavaScript console errors", 
                  f"Console errors detected during page load: {console_errors}",
                  "Load page and check console", "No console errors", "; ".join(console_errors))
        return {"console_errors": f"FAIL: {len(console_errors)} errors"}
    else:
        print("✓ No console errors - PASS")
        return {"console_errors": "PASS"}


async def test_responsive_layout(page):
    """Test responsive layout at different viewport sizes."""
    print("\n=== Testing Responsive Layout ===")
    results = {}
    
    try:
        # Test mobile viewport
        await page.set_viewport_size({"width": 375, "height": 667})
        await page.wait_for_timeout(500)
        
        # Check if file-info stacks vertically (grid-template-columns: 1fr)
        file_info = await page.query_selector(".file-info")
        if file_info:
            styles = await file_info.evaluate("el => getComputedStyle(el).gridTemplateColumns")
            print(f"  Mobile file-info gridTemplateColumns: {styles}")
            if "1fr" in styles and "1fr 1fr 1fr" not in styles:
                print("✓ Mobile layout - PASS (file-info stacks vertically)")
                results["mobile_layout"] = "PASS"
            else:
                print(f"⚠ Mobile layout - PARTIAL (grid: {styles})")
                results["mobile_layout"] = "PARTIAL"
        
        # Test desktop viewport
        await page.set_viewport_size({"width": 1280, "height": 720})
        await page.wait_for_timeout(500)
        
        file_info = await page.query_selector(".file-info")
        if file_info:
            styles = await file_info.evaluate("el => getComputedStyle(el).gridTemplateColumns")
            print(f"  Desktop file-info gridTemplateColumns: {styles}")
            if "1fr 1fr 1fr" in styles or styles.count("1fr") >= 3:
                print("✓ Desktop layout - PASS (file-info 3 columns)")
                results["desktop_layout"] = "PASS"
            else:
                print(f"⚠ Desktop layout - PARTIAL (grid: {styles})")
                results["desktop_layout"] = "PARTIAL"
        
    except Exception as e:
        print(f"✗ Responsive layout - FAIL: {e}")
        results["responsive"] = f"FAIL: {e}"
    
    return results


async def run_all_tests():
    """Run all tests and return aggregated results."""
    all_results = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        # Enable request/response logging
        failed_requests = []
        page.on("requestfailed", lambda req: failed_requests.append({
            "url": req.url,
            "failure": req.failure
        }))
        
        page.on("response", lambda resp: failed_requests.append({
            "url": resp.url,
            "status": resp.status
        }) if resp.status >= 400 else None)
        
        # Run test suites
        all_results["api"] = await test_api_endpoints(page)
        all_results["ui"] = await test_ui_workflow(page)
        all_results["edge_cases"] = await test_edge_cases(page)
        all_results["output_verification"] = await test_output_verification(page)
        all_results["direct_script_test"] = await test_replacement_multiple_occurrences_directly()
        all_results["console"] = await check_console_errors(page)
        all_results["responsive"] = await test_responsive_layout(page)
        
        # Check for failed network requests
        if failed_requests:
            print(f"\n⚠ Failed network requests ({len(failed_requests)}):")
            for req in failed_requests[:10]:
                print(f"  - {req.get('url', 'N/A')}: {req.get('failure', req.get('status', 'N/A'))}")
            all_results["network"] = f"PARTIAL: {len(failed_requests)} failed requests"
        else:
            print("\n✓ No failed network requests - PASS")
            all_results["network"] = "PASS"
        
        await browser.close()
    
    return all_results


def print_summary(results):
    """Print a summary of all test results."""
    print("\n" + "="*60)
    print("QA TEST SUMMARY")
    print("="*60)
    
    total_tests = 0
    passed = 0
    failed = 0
    partial = 0
    skipped = 0
    
    for category, tests in results.items():
        if not isinstance(tests, dict):
            continue
        print(f"\n{category.upper()}:")
        for test_name, result in tests.items():
            total_tests += 1
            if result == "PASS":
                passed += 1
                status = "✓ PASS"
            elif result == "SKIP":
                skipped += 1
                status = "⚠ SKIP"
            elif isinstance(result, str) and result.startswith("PARTIAL"):
                partial += 1
                status = f"~ PARTIAL"
            else:
                failed += 1
                status = f"✗ FAIL"
            print(f"  {test_name}: {status}")
            if result not in ("PASS", "SKIP"):
                print(f"    Details: {result}")
    
    print("\n" + "-"*60)
    print(f"TOTAL: {total_tests} | PASS: {passed} | FAIL: {failed} | PARTIAL: {partial} | SKIP: {skipped}")
    print("-"*60)
    
    return failed == 0


def print_issues_report():
    """Print detailed issues report."""
    print("\n" + "="*60)
    print("DETAILED ISSUES REPORT")
    print("="*60)
    
    if not issues:
        print("No issues found!")
        return
    
    # Group by severity
    severity_order = ["critical", "high", "medium", "low"]
    for severity in severity_order:
        severity_issues = [i for i in issues if i["severity"] == severity]
        if not severity_issues:
            continue
        print(f"\n--- {severity.upper()} SEVERITY ({len(severity_issues)} issues) ---")
        for idx, issue in enumerate(severity_issues, 1):
            print(f"\n  {idx}. [{issue['category']}] {issue['title']}")
            print(f"     Description: {issue['description']}")
            print(f"     Steps to Reproduce: {issue['steps_to_reproduce']}")
            print(f"     Expected: {issue['expected']}")
            print(f"     Actual: {issue['actual']}")
    
    print("\n" + "="*60)
    print(f"TOTAL ISSUES: {len(issues)}")
    for severity in severity_order:
        count = len([i for i in issues if i["severity"] == severity])
        if count > 0:
            print(f"  {severity.upper()}: {count}")
    print("="*60)


if __name__ == "__main__":
    print("Starting comprehensive QA tests for pdf-text-replacer-app...")
    print(f"Base URL: {BASE_URL}")
    print(f"Project root: {PROJECT_ROOT}")
    
    results = asyncio.run(run_all_tests())
    success = print_summary(results)
    print_issues_report()
    
    # Save results to file
    with open(PROJECT_ROOT / "qa_results.json", "w") as f:
        json.dump({
            "test_results": results,
            "issues": issues
        }, f, indent=2)
    print(f"\nResults saved to {PROJECT_ROOT / 'qa_results.json'}")
    
    sys.exit(0 if success else 1)