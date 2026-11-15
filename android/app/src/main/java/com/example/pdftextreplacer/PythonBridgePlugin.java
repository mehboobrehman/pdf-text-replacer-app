package com.example.pdftextreplacer;

import android.util.Base64;
import android.util.Log;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;

@CapacitorPlugin(name = "PythonBridge")
public class PythonBridgePlugin extends Plugin {
    private static final String TAG = "PythonBridgePlugin";

    @Override
    public void load() {
        super.load();
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(getContext()));
        }
    }

    @PluginMethod
    public void uploadPdf(PluginCall call) {
        String base64Data = call.getString("data");
        String filename = call.getString("filename", "document.pdf");

        if (base64Data == null) {
            call.reject("Missing file data");
            return;
        }

        try {
            byte[] decodedBytes = Base64.decode(base64Data, Base64.DEFAULT);
            File uploadDir = new File(getContext().getFilesDir(), "uploaded");
            if (!uploadDir.exists()) {
                uploadDir.mkdirs();
            }

            String saveName = System.currentTimeMillis() + "_" + filename;
            File outFile = new File(uploadDir, saveName);
            FileOutputStream fos = new FileOutputStream(outFile);
            fos.write(decodedBytes);
            fos.close();

            JSObject ret = new JSObject();
            ret.put("path", outFile.getAbsolutePath());
            ret.put("filename", saveName);
            call.resolve(ret);
        } catch (Exception e) {
            Log.e(TAG, "Failed to save PDF", e);
            call.reject("Failed to save PDF: " + e.getMessage());
        }
    }

    @PluginMethod
    public void replaceText(PluginCall call) {
        String pdfPath = call.getString("pdf_path");
        String searchText = call.getString("search_text");
        String replaceText = call.getString("replace_text");

        if (pdfPath == null || searchText == null || replaceText == null) {
            call.reject("Missing required parameters: pdf_path, search_text, replace_text");
            return;
        }

        try {
            Python py = Python.getInstance();
            PyObject pyModule = py.getModule("server_bridge");
            PyObject result = pyModule.callAttr("replace_text_bridge", pdfPath, searchText, replaceText);

            JSObject ret = new JSObject();
            ret.put("stdout", result.get("stdout").toString());
            ret.put("stderr", result.get("stderr").toString());
            ret.put("returncode", result.get("returncode").toInt());
            ret.put("output", result.get("output") != null ? result.get("output").toString() : null);
            ret.put("output_name", result.get("output_name") != null ? result.get("output_name").toString() : null);
            call.resolve(ret);
        } catch (Exception e) {
            Log.e(TAG, "Failed to execute replacement", e);
            call.reject("Failed to execute replacement: " + e.getMessage());
        }
    }

    @PluginMethod
    public void previewPdf(PluginCall call) {
        String pdfPath = call.getString("pdf_path");
        String mode = call.getString("mode", "text");

        if (pdfPath == null) {
            call.reject("Missing pdf_path");
            return;
        }

        try {
            Python py = Python.getInstance();
            PyObject pyModule = py.getModule("server_bridge");
            PyObject result = pyModule.callAttr("preview_pdf_bridge", pdfPath, mode);

            JSObject ret = new JSObject();
            ret.put("pages", result.get("pages") != null ? result.get("pages").toInt() : 0);
            ret.put("char_count", result.get("char_count") != null ? result.get("char_count").toInt() : 0);
            ret.put("sample", result.get("sample") != null ? result.get("sample").toString() : "");
            ret.put("error", result.get("error") != null ? result.get("error").toString() : null);
            call.resolve(ret);
        } catch (Exception e) {
            Log.e(TAG, "Failed to preview PDF", e);
            call.reject("Failed to preview PDF: " + e.getMessage());
        }
    }

    @PluginMethod
    public void getOutputBase64(PluginCall call) {
        String outputName = call.getString("output_name");
        if (outputName == null) {
            call.reject("Missing output_name");
            return;
        }

        try {
            File outputDir = new File(getContext().getFilesDir(), "output");
            File outFile = new File(outputDir, outputName);
            if (!outFile.exists()) {
                call.reject("Output file not found");
                return;
            }

            byte[] bytes = org.apache.commons.io.FileUtils.readFileToByteArray(outFile);
            String base64 = Base64.encodeToString(bytes, Base64.NO_WRAP);

            JSObject ret = new JSObject();
            ret.put("base64", base64);
            ret.put("filename", outputName);
            call.resolve(ret);
        } catch (Exception e) {
            Log.e(TAG, "Failed to read output file", e);
            call.reject("Failed to read output file: " + e.getMessage());
        }
    }
}
