import { escHtml, getLanguage, renderMarkdown, strings, toast } from './ui.js';

const messagesEl    = document.getElementById('messages');
const questionInput = document.getElementById('questionInput');
const sendBtn       = document.getElementById('sendBtn');
let isLoading = false;
let history = [];  // [{role: "user"|"assistant", content: "..."}]
let activeController = null;
let chatGeneration = 0;

function clearChat() {
  chatGeneration += 1;
  if (activeController) activeController.abort();
  activeController = null;
  isLoading = false;
  sendBtn.disabled = false;
  history = [];
  messagesEl.innerHTML = `
    <div class="welcome" id="welcome">
      <div class="icon">💬</div>
      <h2 id="wTitle">${strings().wTitle}</h2>
      <p id="wDesc">${strings().wDesc}</p>
    </div>`;
  questionInput.focus();
}

function addUserMessage(content) {
  document.getElementById('welcome')?.remove();
  const el = document.createElement('div');
  el.className = 'message user';
  el.innerHTML = `<div class="avatar">🧑</div><div><div class="bubble">${escHtml(content).replace(/\n/g, '<br>')}</div></div>`;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addStreamingBubble() {
  const welcome = document.getElementById('welcome');
  if (welcome) welcome.remove();
  const el = document.createElement('div');
  el.className = 'message assistant';
  el.innerHTML = `
    <div class="avatar">🤖</div>
    <div class="msg-body">
      <div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>
    </div>`;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function updateBubble(el, text) {
  const bubble = el.querySelector('.bubble');
  bubble.classList.add('md');
  bubble.innerHTML = renderMarkdown(text);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addCopyBtn(el, text) {
  const btn = document.createElement('button');
  btn.className = 'copy-btn';
  btn.textContent = strings().copy;
  btn.onclick = async () => {
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;opacity:0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      btn.textContent = strings().copied;
      btn.classList.add('ok');
      setTimeout(() => { btn.textContent = strings().copy; btn.classList.remove('ok'); }, 2000);
    } catch(e) {
      btn.textContent = strings().copyFailed;
      setTimeout(() => { btn.textContent = strings().copy; }, 2000);
    }
  };
  el.querySelector('.msg-body').appendChild(btn);
}

function attachMeta(el, sources, chunks) {
  const l = strings();
  const body = el.querySelector('.msg-body');

  if (sources.length) {
    const src = document.createElement('div');
    src.className = 'sources';
    src.innerHTML = `<span class="sources-label">${l.sourcesLabel}</span>
      ${sources.map(s => `<span class="source-chip">${escHtml(s)}</span>`).join('')}`;
    body.appendChild(src);
  }

  if (chunks.length) {
    const btn = document.createElement('button');
    btn.className = 'chunks-toggle';
    btn.textContent = l.showChunks;
    const list = document.createElement('div');
    list.className = 'chunks-list';
    list.style.display = 'none';
    list.innerHTML = chunks.map(c => `
      <div class="chunk-item">
        <div class="chunk-source">📎 ${escHtml(c.source)}</div>
        ${escHtml(c.text)}
      </div>`).join('');
    btn.onclick = () => {
      const open = list.style.display !== 'none';
      list.style.display = open ? 'none' : 'flex';
      btn.textContent = open ? strings().showChunks : strings().hideChunks;
    };
    body.appendChild(btn);
    body.appendChild(list);
  }
}

async function sendQuestion() {
  const q = questionInput.value.trim();
  if (!q || isLoading) return;
  const generation = chatGeneration;
  const controller = new AbortController();
  activeController = controller;
  isLoading = true;
  sendBtn.disabled = true;
  questionInput.value = '';
  questionInput.style.height = 'auto';

  addUserMessage(q);
  const assistantEl = addStreamingBubble();

  try {
    const res = await fetch('/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, history: requestHistory() }),
      signal: controller.signal
    });
    if (generation !== chatGeneration) return;

    if (!res.ok) {
      const msg = await res.text().catch(() => `HTTP ${res.status}`);
      updateBubble(assistantEl, `Error ${res.status}: ${msg}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let completed = false;

    while (true) {
      const { done, value } = await reader.read();
      if (generation !== chatGeneration) { await reader.cancel(); return; }
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue;
        const evt = JSON.parse(part.slice(6));
        if (evt.type === 'token') {
          updateBubble(assistantEl, (assistantEl._text = (assistantEl._text || '') + evt.content));
        } else if (evt.type === 'done') {
          if (completed) continue;
          completed = true;
          updateBubble(assistantEl, evt.answer);
          addCopyBtn(assistantEl, evt.answer);
          attachMeta(assistantEl, evt.sources, evt.chunks);
          history.push({ role: 'user', content: q });
          history.push({ role: 'assistant', content: evt.answer });
          history = history.slice(-6);
        } else if (evt.type === 'error') {
          throw new Error(evt.message || strings().errServer);
        }
      }
    }
    if (!completed) throw new Error('The response stream ended before completion');
  } catch (e) {
    if (generation !== chatGeneration || e?.name === 'AbortError') return;
    updateBubble(assistantEl, strings().errServer + (e?.message ? ` (${e.message})` : ''));
  } finally {
    if (generation === chatGeneration) {
      activeController = null;
      isLoading = false;
      sendBtn.disabled = false;
      questionInput.focus();
    }
  }
}

function requestHistory() {
  // Keep whole turns within the API budget; never truncate displayed answers.
  const recent = history.slice(-6);
  let bounded = [];
  let omitted = false;
  for (let i = 0; i < recent.length; i += 2) {
    const turn = recent.slice(i, i + 2);
    if (turn.some(message => message.content.length > 8000)) { omitted = true; continue; }
    bounded.push(...turn);
  }
  while (bounded.reduce((size, message) => size + message.content.length, 0) > 24000) {
    bounded = bounded.slice(2);
    omitted = true;
  }
  if (omitted) toast(getLanguage() === 'zh'
    ? '部分较长对话未加入本次上下文；需要时请在问题中重述关键信息。'
    : 'Some longer turns were omitted from follow-up context. Restate key details if needed.', 6500);
  return bounded;
}

export function initializeChat() {
  sendBtn.addEventListener('click', sendQuestion);
  questionInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); }
  });
  questionInput.addEventListener('input', () => {
    questionInput.style.height = 'auto';
    questionInput.style.height = Math.min(questionInput.scrollHeight, 120) + 'px';
  });
  document.getElementById('newChatBtn').addEventListener('click', clearChat);
}
