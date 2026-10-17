import { escHtml, getLanguage, strings, toast } from './ui.js';

let currentDocs = [];

async function loadDocs() {
  const res  = await fetch('/documents');
  const data = await res.json();
  renderDocs(data.documents);
}

function renderDocs(docs) {
  currentDocs = docs;
  const l = strings();
  document.getElementById('docCount').textContent = docs.length ? `(${docs.length})` : '';
  const list = document.getElementById('docsList');
  if (!docs.length) {
    list.innerHTML = `<div class="empty-docs" id="emptyDocs">${l.emptyDocs}</div>`;
    return;
  }
  // EN: Use escHtml() on filenames and data attributes instead of inline onclick
  //     to prevent XSS from maliciously crafted filenames.
  // ZH: 对文件名使用 escHtml() 并通过 data 属性传递，
  //     避免恶意文件名通过 inline onclick 注入脚本（XSS）。
  list.innerHTML = docs.map(d => {
    const icon = d.endsWith('.pdf') ? '📕' : d.endsWith('.docx') ? '📝' : d.endsWith('.md') ? '📋' : '📄';
    const safe = escHtml(d);
    return `<div class="doc-item" data-filename="${safe}">
      <span>${icon}</span>
      <span class="doc-name" title="${safe}">${safe}</span>
      <button class="doc-delete" title="${l.deleteTitle}">✕</button>
    </div>`;
  }).join('');
  // EN: Attach delete handlers via event listeners, not inline onclick.
  // ZH: 通过事件监听器绑定删除操作，不使用 inline onclick。
  list.querySelectorAll('.doc-delete').forEach(btn => {
    btn.addEventListener('click', () => deleteDoc(btn.closest('.doc-item').dataset.filename));
  });
}

async function deleteDoc(filename) {
  try {
    const response = await fetch('/documents/' + encodeURIComponent(filename), { method: 'DELETE' });
    if (!response.ok) throw new Error('Delete failed (HTTP ' + response.status + ')');
    toast(strings().toastRemoved(filename));
    await loadDocs();
  } catch (error) {
    toast(strings().toastErr(error.message));
  }
}

// ── Upload ─────────────────────────────────────────────────────────────────
async function uploadFile(file) {
  if (currentDocs.includes(file.name)) {
    const msg = getLanguage() === 'zh'
      ? `"${file.name}" 已存在，替换为新版本？`
      : `"${file.name}" is already indexed. Replace it?`;
    if (!confirm(msg)) return;
  }

  const form = new FormData();
  form.append('file', file);

  // Show staged status messages so users know OCR uploads are still running
  const msgEl = document.getElementById('uploadingMsg');
  const isZh = getLanguage() === 'zh';
  const stages = isZh
    ? ['⏳ 上传中…', '📄 提取文本…', '🔍 OCR 识别中，预计 30–60 秒…']
    : ['⏳ Uploading…', '📄 Extracting text…', '🔍 OCR processing (~30–60s)…'];
  msgEl.textContent = stages[0];
  msgEl.classList.add('show');
  const t1 = setTimeout(() => { msgEl.textContent = stages[1]; }, 4000);
  const t2 = setTimeout(() => { msgEl.textContent = stages[2]; }, 14000);

  try {
    const res  = await fetch('/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Upload failed');
    toast(strings().toastIndexed(data.filename, data.chunks));
    loadDocs();
  } catch (e) {
    toast(strings().toastErr(e.message));
  } finally {
    clearTimeout(t1);
    clearTimeout(t2);
    msgEl.classList.remove('show');
  }
}

const fileInput  = document.getElementById('fileInput');
const uploadZone = document.getElementById('uploadZone');

export function initializeDocuments() {
  fileInput.addEventListener('change', async () => {
    for (const f of fileInput.files) await uploadFile(f);
    fileInput.value = '';
  });
  uploadZone.addEventListener('dragover',  e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
  uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
  uploadZone.addEventListener('drop', async e => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    for (const f of e.dataTransfer.files) await uploadFile(f);
  });
  return loadDocs();
}
