const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const browseButton = document.getElementById('browseButton');
const editorSection = document.getElementById('editorSection');
const uploadSection = document.getElementById('uploadSection');
const fileNameEl = document.getElementById('fileName');
const fileSizeEl = document.getElementById('fileSize');
const filePathEl = document.getElementById('filePath');
const searchTextInput = document.getElementById('searchText');
const replaceTextInput = document.getElementById('replaceText');
const replaceButton = document.getElementById('replaceButton');
const previewButton = document.getElementById('previewButton');
const saveButton = document.getElementById('saveButton');
const newFileButton = document.getElementById('newFileButton');
const statusEl = document.getElementById('status');
const previewSection = document.getElementById('previewSection');
const previewMeta = document.getElementById('previewMeta');
const previewBody = document.getElementById('previewBody');
const previewTitle = document.getElementById('previewTitle');
const ocrModeInput = document.getElementById('ocrMode');

let currentUploadPath = null;
let lastOutputName = null;

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return '-';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) {
    bytes /= 1024;
    i += 1;
  }
  return `${bytes.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function showStatus(message, type = 'info') {
  statusEl.textContent = message;
  statusEl.className = 'status ' + type;
}

function clearStatus() {
  statusEl.textContent = '';
  statusEl.className = 'status';
}

function setEditorVisible(visible) {
  editorSection.classList.toggle('hidden', !visible);
  uploadSection.classList.toggle('hidden', visible);
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file, file.name);
  const response = await fetch('/api/upload', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || 'Upload failed');
  }
  return response.json();
}

async function loadFile(file) {
  if (!file) return;
  if (file.type && file.type !== 'application/pdf') {
    showStatus('Please select a PDF file.', 'error');
    return;
  }

  currentUploadPath = null;
  lastOutputName = null;

  filePathEl.textContent = 'uploaded';
  fileNameEl.textContent = file.name || '-';
  fileSizeEl.textContent = formatBytes(file.size);
  searchTextInput.value = '';
  replaceTextInput.value = '';
  clearStatus();
  setEditorVisible(true);

  try {
    const data = await uploadFile(file);
    currentUploadPath = data.path;
    filePathEl.textContent = data.path || 'uploaded';
  } catch (err) {
    showStatus('Upload failed: ' + err.message, 'error');
  }
}

function handleFile(file) {
  loadFile(file);
}

function openFileDialog() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'application/pdf';
  input.onchange = () => {
    if (input.files && input.files[0]) {
      handleFile(input.files[0]);
    }
  };
  input.click();
}

function newFile() {
  currentUploadPath = null;
  lastOutputName = null;
  fileInput.value = '';
  ocrModeInput.checked = false;
  saveButton.disabled = true;
  clearStatus();
  setEditorVisible(false);
}

async function replaceText() {
  const searchText = searchTextInput.value;
  const replaceTextVal = replaceTextInput.value;

  if (!searchText) {
    showStatus('Enter search text.', 'error');
    return;
  }
  if (!currentUploadPath) {
    showStatus('Upload a PDF first.', 'error');
    return;
  }

  replaceButton.disabled = true;
  showStatus('Replacing text...', 'info');

  try {
    const res = await fetch('/api/replace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pdf_path: currentUploadPath,
        search_text: searchText,
        replace_text: replaceTextVal,
      }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.stderr || data.stdout || ('HTTP ' + res.status));
    }

    if (data.returncode !== 0) {
      const msg = data.stderr || data.stdout || 'Replacement failed.';
      showStatus('Error: ' + msg, 'error');
    } else {
      lastOutputName = data.output_name || '';
      saveButton.disabled = !lastOutputName;
      showStatus('Done. Click Save to choose where to store the output.', 'success');
    }
  } catch (err) {
    showStatus('Error: ' + err.message, 'error');
  } finally {
    replaceButton.disabled = false;
  }
}

async function saveOutputWithDialog() {
  if (!lastOutputName) {
    showStatus('Run Replace first so there is a result to save.', 'error');
    return;
  }

  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: lastOutputName,
        types: [
          {
            description: 'PDF',
            accept: { 'application/pdf': ['.pdf'] },
          },
        ],
      });
      const writable = await handle.createWritable();
      const response = await fetch('/output/' + encodeURIComponent(lastOutputName));
      if (!response.ok) {
        throw new Error('Failed to read output PDF');
      }
      const blob = await response.blob();
      await writable.write(blob);
      await writable.close();
      showStatus('Saved: ' + handle.name, 'success');
      return;
    } catch (err) {
      if (err.name === 'AbortError') {
        showStatus('Save canceled.', 'info');
        return;
      }
      showStatus('Save failed: ' + err.message, 'error');
      return;
    }
  }

  const a = document.createElement('a');
  a.href = '/output/' + encodeURIComponent(lastOutputName);
  a.download = lastOutputName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showStatus('Download started: ' + lastOutputName, 'success');
}

async function previewPdf() {
  if (!currentUploadPath) {
    showStatus('Upload a PDF first.', 'error');
    return;
  }

  const useOcr = ocrModeInput.checked;
  previewButton.disabled = true;
  showStatus(useOcr ? 'Scanning PDF with OCR...' : 'Scanning PDF text...', 'info');
  previewTitle.textContent = useOcr ? 'PDF OCR Preview' : 'PDF Preview';

  try {
    const res = await fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pdf_path: currentUploadPath, mode: useOcr ? 'ocr' : 'text' }),
    });

    const data = await res.json();
    if (!res.ok || (data && data.error)) {
      previewMeta.textContent = '';
      previewBody.textContent = (data && data.error) ? data.error : ('HTTP ' + res.status);
      previewSection.classList.remove('hidden');
      showStatus('Preview failed: ' + ((data && data.error) ? data.error : 'HTTP ' + res.status), 'error');
      return;
    }

    previewMeta.textContent = ((data.pages || '?') + ' pages · ' + (data.char_count || '0') + ' chars') + (useOcr ? ' (OCR)' : '');
    previewBody.textContent = data.sample || '(no extractable text)';
    previewSection.classList.remove('hidden');
    showStatus(useOcr ? 'OCR preview loaded.' : 'Preview loaded. Use this to see searchable text.', 'success');
  } catch (err) {
    showStatus('Error: ' + err.message, 'error');
  } finally {
    previewButton.disabled = false;
  }
}

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  handleFile(file);
});

browseButton.addEventListener('click', (e) => {
  e.stopPropagation();
  openFileDialog();
});

fileInput.addEventListener('change', () => {
  const file = fileInput.files && fileInput.files[0];
  handleFile(file);
});

replaceButton.addEventListener('click', replaceText);
previewButton.addEventListener('click', previewPdf);
saveButton.addEventListener('click', saveOutputWithDialog);
newFileButton.addEventListener('click', newFile);

document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'o') {
    e.preventDefault();
    openFileDialog();
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault();
    void saveOutputWithDialog();
  }
});
