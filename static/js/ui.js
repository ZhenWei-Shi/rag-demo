function toggleSidebar() {
  document.querySelector('.sidebar').classList.toggle('open');
  document.getElementById('sidebarOverlay').classList.toggle('show');
}

// ── i18n ───────────────────────────────────────────────────────────────────
const t = {
  en: {
    newChat:      'New chat',
    langBtn:      '中文',
    hTitle:       'RAG Document Q&A',
    sUploadTitle: 'Upload Document',
    sUploadHint:  '<strong>Click or drag &amp; drop</strong><br>PDF, DOCX, TXT, MD',
    indexing:     '⏳ Indexing…',
    privacyNotice: 'Shared demo: uploads are visible to all visitors. Use public sample files only.',
    sDocsTitle:   'Documents',
    emptyDocs:    'No documents yet.<br>Upload a file to get started.',
    wTitle:       'Ask your documents anything',
    wDesc:        'Upload a PDF, DOCX, TXT or MD file, then ask questions about its content. Answers are grounded in your documents.',
    placeholder:  'Ask a question… (Enter to send)',
    showChunks:   'Show retrieved chunks',
    hideChunks:   'Hide chunks',
    sourcesLabel: 'Sources:',
    deleteTitle:  'Remove',
    copy: 'Copy', copied: '✓ Copied', copyFailed: 'Failed',
    errServer:    'The answer could not be completed. Please retry.',
    toastIndexed: (f, n) => `✓ Indexed: ${f} (${n} chunks)`,
    toastRemoved: f => `Removed: ${f}`,
    toastErr:     msg => `✗ ${msg}`,
  },
  zh: {
    newChat:      '新对话',
    langBtn:      'English',
    hTitle:       'RAG 文档问答',
    sUploadTitle: '上传文档',
    sUploadHint:  '<strong>点击或拖拽文件</strong><br>支持 PDF、DOCX、TXT、MD 格式',
    indexing:     '⏳ 索引中…',
    privacyNotice: '共享演示：上传文档对所有访客可见，请仅使用公开样例文件。',
    sDocsTitle:   '文档列表',
    emptyDocs:    '暂无文档。<br>上传文件开始使用。',
    wTitle:       '向你的文档提问',
    wDesc:        '上传 PDF、DOCX、TXT 或 MD 文件，然后就文档内容提问。答案直接来源于你的文档。',
    placeholder:  '输入问题…（Enter 发送，Shift+Enter 换行）',
    showChunks:   '查看检索片段',
    hideChunks:   '收起片段',
    sourcesLabel: '来源：',
    deleteTitle:  '删除',
    copy: '复制', copied: '✓ 已复制', copyFailed: '复制失败',
    errServer:    '回答未能完成，请重试。',
    toastIndexed: (f, n) => `✓ 已索引：${f}（${n} 个片段）`,
    toastRemoved: f => `已删除：${f}`,
    toastErr:     msg => `✗ ${msg}`,
  }
};

let lang = 'en';

function toggleLang() {
  lang = lang === 'en' ? 'zh' : 'en';
  applyLang();
}

function applyLang() {
  const l = t[lang];
  document.documentElement.lang = lang;
  document.querySelectorAll('.sources-label').forEach(el => { el.textContent = l.sourcesLabel; });
  document.querySelectorAll('.chunks-toggle').forEach(btn => {
    btn.textContent = btn.nextElementSibling.style.display === 'none' ? l.showChunks : l.hideChunks;
  });
  document.querySelectorAll('.doc-delete').forEach(btn => { btn.title = l.deleteTitle; });
  document.querySelectorAll('.copy-btn').forEach(btn => { btn.textContent = btn.classList.contains('ok') ? l.copied : l.copy; });
  document.getElementById('langBtn').textContent     = l.langBtn;
  document.getElementById('hTitle').textContent      = l.hTitle;
  document.getElementById('sUploadTitle').textContent = l.sUploadTitle;
  document.getElementById('sUploadHint').innerHTML   = l.sUploadHint;
  document.getElementById('privacyNotice').textContent = l.privacyNotice;
  if (document.getElementById('wTitle')) document.getElementById('wTitle').textContent = l.wTitle;
  if (document.getElementById('wDesc')) document.getElementById('wDesc').textContent = l.wDesc;
  document.getElementById('questionInput').placeholder = l.placeholder;
  document.getElementById('sNewChat').textContent = l.newChat;
  const ed = document.getElementById('emptyDocs');
  if (ed) ed.innerHTML = l.emptyDocs;
  // docs title (keep count span)
  const count = document.getElementById('docCount').outerHTML;
  document.getElementById('sDocsTitle').innerHTML = l.sDocsTitle + ' ' + count;
}

// ── Toast ──────────────────────────────────────────────────────────────────
export function toast(msg, ms = 3000) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), ms);
}


export function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

export function renderMarkdown(text) {
  // Sanitize after Markdown parsing, for every partial/final/error rendering.
  if (!window.DOMPurify || !window.marked) return escHtml(text).replace(/\n/g, '<br>');
  return DOMPurify.sanitize(marked.parse(String(text)), {
    USE_PROFILES: { html: true },
    SANITIZE_NAMED_PROPS: true,
    FORBID_TAGS: ['style', 'form', 'input', 'button', 'textarea', 'select'],
    FORBID_ATTR: ['style']
  });
}


export const strings = () => t[lang];
export const getLanguage = () => lang;

export function initializeUi() {
  if (window.marked) marked.use({ breaks: true, gfm: true });
  document.getElementById('menuBtn').addEventListener('click', toggleSidebar);
  document.getElementById('sidebarOverlay').addEventListener('click', toggleSidebar);
  document.getElementById('langBtn').addEventListener('click', toggleLang);
}
