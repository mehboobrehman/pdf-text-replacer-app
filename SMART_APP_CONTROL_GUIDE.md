# Windows Smart App Control & Distribution Guide for PDF Text Replacer

This document outlines the investigation, root causes, and remediation strategies for Windows Smart App Control (SAC) and Windows Defender blocking `PDFTextReplacer.exe`.

---

## 1. Root Cause Analysis: Why Windows Smart App Control Blocks PyInstaller Executables

Windows Smart App Control (SAC) and Windows Defender SmartScreen use reputation-based heuristics to evaluate unsigned or unverified executables. PyInstaller-packaged applications are frequently flagged or blocked by SAC due to specific characteristics:

1. **Lack of a Trusted Digital Signature:** 
   SAC strictly blocks any executable that is not digitally signed by a trusted Certificate Authority (CA) recognized by the Windows Root Certificate Program, unless the user has opted out of SAC or runs the app in Evaluation Mode.
2. **Heuristic Detection (Unpacked Bootloader / Packed Payload):**
   PyInstaller bundles Python DLLs, a standard Python runtime interpreter, extension modules (`.pyd` files like PyMuPDF/fitz, PIL), and user scripts (`app_launcher.py`, `server.py`) into a single binary package containing a bootloader (`runw.exe`) that extracts payload to `%TEMP\_MEIxxxxxx%`. This extraction and dynamic loading pattern resembles techniques used by certain packed malware, triggering heuristic alarms in security software.
3. **Missing Metadata / Manifest / Company Identity:**
   Unsigned binaries lacking comprehensive file metadata, proper executable manifests (requesting execution levels or DPI awareness), or publisher company names have low trust reputation scores.

---

## 2. Comprehensive Mitigation & Resolution Strategies

To ensure users can run `PDFTextReplacer.exe` without Smart App Control or SmartScreen blocking, implement the following multi-layered approach:

### Strategy A: Code Signing (The Only Direct Solution for SAC Enforcement)
Smart App Control **requires** a valid Authenticode digital signature from a trusted CA (e.g., DigiCert, Sectigo, SSL.com, or a self-signed certificate installed in the Trusted Root Certification Authorities store for internal distribution).

#### 1. Obtaining / Generating a Certificate:
* **Production / Public Distribution:** Obtain an OV (Organization Validation) or EV (Extended Validation) Code Signing Certificate from a trusted CA.
* **Internal / Self-Signed Distribution (Testing / Enterprise Deployment):**
  Generate a self-signed certificate via PowerShell:
  ```powershell
  $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=PDF Text Replacer, O=PDF Text Replacer" -CertStoreLocation "Cert:\CurrentUser\My" -KeyExportPolicy Exportable
  Export-Certificate -Cert $cert -FilePath "PDFTextReplacer.cer"
  # To trust locally (for testing):
  Import-Certificate -FilePath "PDFTextReplacer.cer" -CertStoreLocation "Cert:\LocalMachine\TrustedPeople"
  ```

#### 2. Signing the Executable (`signtool.exe`):
Once signed with a trusted certificate, SAC will allow execution:
```cmd
signtool sign /fd SHA256 /a /f PDFTextReplacer.pfx /p "YourPassword" /tr http://timestamp.digicert.com /td SHA256 dist\PDFTextReplacer.exe
```

---

### Strategy B: Enhancing Metadata, Manifest, and PyInstaller Spec (Heuristic Minimization)
Even if an app is unsigned or distributed in evaluation/permissive environments, improving metadata and manifests drastically reduces false-positive heuristics.

1. **Version Info Resource (`version_info.txt`):**
   Ensure company name, product name, file version, and original filename are fully populated (already configured in `version_info.txt`).
2. **Executable Manifest (`manifest.xml`):**
   Include an execution manifest specifying UAC requirements (`asInvoker`), DPI awareness, and supported OS versions so Windows recognizes it as a modern, well-behaved Win32 application.
   Example `manifest.xml`:
   ```xml
   <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
   <assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
     <assemblyIdentity version="1.0.0.0" processorArchitecture="*" name="PDFTextReplacer" type="win32"/>
     <description>PDF Text Replacer Desktop Application</description>
     <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
       <security>
         <requestedPrivileges>
           <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
         </requestedPrivileges>
       </security>
     </trustInfo>
     <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
       <application>
         <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
       </application>
     </compatibility>
   </assembly>
   ```
   *In `PDFTextReplacer.spec`, pass `manifest='manifest.xml'` to `EXE()`.*

---

### Strategy C: Alternative Distribution & Packaging Methods
If direct `.exe` execution triggers strict SAC policies on end-user machines where SAC cannot be disabled:

1. **Installer / MSI Packaging (Inno Setup / WiX):**
   Package `PDFTextReplacer.exe` and its supporting folders inside an installer (.msi or .exe generated via Inno Setup). Installers signed by a CA inherit trust for the installed files. Furthermore, enterprise administrators can deploy the MSI via Group Policy or Intune, bypassing SAC restrictions.
2. **Zip Archive with PowerShell / Batch Launcher (`launch.ps1`):**
   Instead of distributing a monolithic PyInstaller `.exe` that triggers heuristic blocks, distribute a `.zip` containing the Python script launcher (`launch.ps1` and `server.py` / `index.html`) running on the user's pre-installed Python runtime. Scripts executed via PowerShell (`launch.ps1`) or Python interpreter are often evaluated differently by Smart App Control compared to standalone packed PyInstaller binaries.
3. **Turning off Smart App Control (End-User Guidance):**
   Note that Windows Smart App Control can only be turned off by resetting Windows or via Windows Security settings if the OS is in evaluation mode. For standard production devices with SAC permanently enforced, **Code Signing with a trusted CA is mandatory**.

---

## Summary Recommendation
1. **For Production Release:** Procure an OV/EV Code Signing Certificate and sign `PDFTextReplacer.exe` using `signtool.exe` with a valid timestamp server.
2. **For Build Hardening:** Include the application manifest (`manifest.xml`) and complete version metadata in `PDFTextReplacer.spec`.
3. **For Alternative Distribution:** Provide an Inno Setup installer package or standard `.zip` with the PowerShell launcher script.
