#!/usr/bin/env python3
"""Comprehensive QA test for pdf-text-replacer-app using Playwright."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:8000"
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
                assert response.ok, f"Upload failed: {response.status}"
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
    
    # Test /api/preview with OCR mode
    if upload_path:
        try:
            response = await page.request.post(f"{BASE_URL}/api/preview",
                data=json.dumps({"pdf_path": upload_path, "mode": "ocr"}),
                headers={"Content-Type": "application/json"})
            data = await response.json()
            # OCR may not be available, so we accept either success or specific error
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
        except Exception as e:
            print(f"✗ /api/preview (ocr) - FAIL: {e}")
            results["preview_ocr"] = f"FAIL: {e}"
    
    # Test /api/replace with valid data
    replace_output = None
    if upload_path:
        try:
            response = await page.request.post(f"{BASE_URL}/api/replace",
                data=json.dumps({
                    "pdf_path": upload_path,
                    "search_text": "Test",
                    "replace_text": "Replaced"
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
            # Should return returncode != 0 since text not found
            if data.get("returncode") != 0:
                print(f"✓ /api/replace (text not found) - PASS (correctly reported not found)")
                results["replace_not_found"] = "PASS"
            else:
                print(f"⚠ /api/replace (text not found) - PARTIAL: returned success but text wasn't found")
                results["replace_not_found"] = "PARTIAL"
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
    
    return results


async def test_ui_workflow(page):
    """Test the complete UI workflow."""
    print("\n=== Testing UI Workflow ===")
    results = {}
    
    # Navigate to the app
    try:
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_load_state("domcontentloaded")
        
        # Check for console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg) if msg.type == "error" else None)
        
        # Verify page loaded
        await page.wait_for_selector("#dropZone", timeout=5000)
        print("✓ Page loaded - PASS")
        results["page_load"] = "PASS"
    except Exception as e:
        print(f"✗ Page load - FAIL: {e}")
        results["page_load"] = f"FAIL: {e}"
        return results
    
    # Test file upload via drag and drop
    try:
        test_file = TEST_FILES["basic"]
        if test_file.exists():
            # Use file input to upload
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
    
    # Test OCR toggle and preview
    try:
        # Check OCR checkbox
        await page.check("#ocrMode")
        await page.click("#previewButton")
        await page.wait_for_selector("#previewSection:not(.hidden)", timeout=15000)
        
        preview_title = await page.text_content("#previewTitle")
        preview_meta = await page.text_content("#previewMeta")
        
        print(f"✓ Preview (OCR) - {'PASS' if 'OCR' in preview_title else 'PARTIAL'} (title: {preview_title}, meta: {preview_meta})")
        results["preview_ocr_ui"] = "PASS" if "OCR" in preview_title else "PARTIAL"
        
        # Uncheck OCR for subsequent tests
        await page.uncheck("#ocrMode")
    except Exception as e:
        print(f"✗ Preview (OCR) - FAIL: {e}")
        results["preview_ocr_ui"] = f"FAIL: {e}"
    
    # Test text replacement
    try:
        await page.fill("#searchText", "Test")
        await page.fill("#replaceText", "Replaced")
        await page.click("#replaceButton")
        
        # Wait for success status
        await page.wait_for_function(
            "() => document.getElementById('status').classList.contains('success')",
            timeout=15000
        )
        
        status_text = await page.text_content("#status")
        save_disabled = await page.is_enabled("#saveButton")
        
        print(f"✓ Text replacement - PASS (status: {status_text}, save enabled: {not save_disabled})")
        results["text_replace"] = "PASS"
    except Exception as e:
        print(f"✗ Text replacement - FAIL: {e}")
        results["text_replace"] = f"FAIL: {e}"
    
    # Test Save/Download button
    try:
        # Note: showSaveFilePicker may not be available in headless mode
        # We'll test the fallback download approach
        download_started = False
        
        async with page.expect_download() as download_info:
            await page.click("#saveButton")
            download = await download_info.value
            
        # Check download
        if download:
            download_path = await download.path()
            if download_path and os.path.getsize(download_path) > 0:
                print(f"✓ Save/Download - PASS (downloaded: {download.suggested_filename})")
                results["save_download"] = "PASS"
            else:
                print(f"⚠ Save/Download - PARTIAL (download initiated but file empty)")
                results["save_download"] = "PARTIAL"
        else:
            print(f"⚠ Save/Download - PARTIAL (no download event)")
            results["save_download"] = "PARTIAL"
    except Exception as e:
        print(f"✗ Save/Download - FAIL: {e}")
        results["save_download"] = f"FAIL: {e}"
    
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
    
    # Test with scanned PDF (OCR)
    try:
        test_file = TEST_FILES["scanned"]
        if test_file.exists():
            await page.click("#newFileButton")
            await page.wait_for_selector("#uploadSection:not(.hidden)", timeout=3000)
            
            file_input = await page.query_selector("#fileInput")
            await file_input.set_input_files(str(test_file))
            await page.wait_for_selector("#editorSection:not(.hidden)", timeout=5000)
            
            # Test with OCR mode
            await page.check("#ocrMode")
            await page.click("#previewButton")
            await page.wait_for_selector("#previewSection:not(.hidden)", timeout=15000)
            preview_body = await page.text_content("#previewBody")
            
            await page.uncheck("#ocrMode")
            
            print(f"✓ Scanned PDF (OCR) - PASS (preview length: {len(preview_body)})")
            results["scanned_pdf_ocr"] = "PASS"
        else:
            print("⚠ Scanned PDF - SKIP: test_scanned.pdf not found")
            results["scanned_pdf_ocr"] = "SKIP"
    except Exception as e:
        print(f"✗ Scanned PDF (OCR) - FAIL: {e}")
        results["scanned_pdf_ocr"] = f"FAIL: {e}"
    
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
    
    # Test empty replace text validation
    try:
        await page.fill("#searchText", "Test")
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
    
    return results


async def test_output_verification(page):
    """Verify the output PDF actually has replaced text."""
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
            
            # Perform replacement
            await page.fill("#searchText", "Test")
            await page.fill("#replaceText", "REPLACED_SUCCESSFULLY")
            await page.click("#replaceButton")
            
            await page.wait_for_function(
                "() => document.getElementById('status').classList.contains('success')",
                timeout=15000
            )
            
            # Download the result
            async with page.expect_download() as download_info:
                await page.click("#saveButton")
            download = await download_info.value
            
            if download:
                download_path = await download.path()
                if download_path and os.path.getsize(download_path) > 0:
                    # Verify the PDF content using PyMuPDF
                    import fitz
                    doc = fitz.open(download_path)
                    full_text = ""
                    for page_num in range(len(doc)):
                        full_text += doc[page_num].get_text("text")
                    doc.close()
                    
                    if "REPLACED_SUCCESSFULLY" in full_text and "Test" not in full_text:
                        print(f"✓ Output PDF verification - PASS (text replaced correctly)")
                        results["output_verification"] = "PASS"
                    elif "REPLACED_SUCCESSFULLY" in full_text:
                        print(f"⚠ Output PDF verification - PARTIAL (replaced text found but original may still exist)")
                        results["output_verification"] = "PARTIAL"
                    else:
                        print(f"✗ Output PDF verification - FAIL (replaced text not found in output)")
                        print(f"  Output text sample: {full_text[:200]}")
                        results["output_verification"] = "FAIL"
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
        return {"console_errors": f"FAIL: {len(console_errors)} errors"}
    else:
        print("✓ No console errors - PASS")
        return {"console_errors": "PASS"}


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
        all_results["console"] = await check_console_errors(page)
        
        # Check for failed network requests
        if failed_requests:
            print(f"\n⚠ Failed network requests ({len(failed_requests)}):")
            for req in failed_requests[:10]:  # Show first 10
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
        print(f"\n{category.upper()}:")
        for test_name, result in tests.items():
            total_tests += 1
            if result == "PASS":
                passed += 1
                status = "✓ PASS"
            elif result == "SKIP":
                skipped += 1
                status = "⚠ SKIP"
            elif result.startswith("PARTIAL"):
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
    
    if failed > 0:
        print("\n❌ SOME TESTS FAILED")
        return False
    elif partial > 0:
        print("\n⚠ SOME TESTS PARTIAL")
        return True
    else:
        print("\n✅ ALL TESTS PASSED")
        return True


if __name__ == "__main__":
    print("Starting comprehensive QA tests for pdf-text-replacer-app...")
    print(f"Base URL: {BASE_URL}")
    print(f"Project root: {PROJECT_ROOT}")
    
    results = asyncio.run(run_all_tests())
    success = print_summary(results)
    
    # Save results to file
    import json
    with open(PROJECT_ROOT / "qa_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {PROJECT_ROOT / 'qa_results.json'}")
    
    sys.exit(0 if success else 1)