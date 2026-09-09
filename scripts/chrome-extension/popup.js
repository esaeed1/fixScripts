'use strict';

// jsPDF loaded from lib/jspdf.umd.min.js
const { jsPDF } = window.jspdf;

// ── State ─────────────────────────────────────────────────────────────────────
let port       = null;
let pdfDoc     = null;
let pageQueue  = [];
let processing = false;
let isCapturing = false;
let bookTitle  = 'VitalSource Book';

// ── DOM helpers ───────────────────────────────────────────────────────────────
const el = (id) => document.getElementById(id);

function showPanel(id) {
  ['panel-not-vs', 'panel-main', 'panel-error'].forEach((p) => {
    el(p).hidden = (p !== id);
  });
}

// ── Tab communication ─────────────────────────────────────────────────────────
async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function msgTab(tabId, msg) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, msg, (res) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(res);
    });
  });
}

function isVS(url) {
  return !!(url && (url.includes('vitalsource.com') || url.includes('chegg.com')));
}

// ── Initialisation ─────────────────────────────────────────────────────────────
async function init() {
  const tab = await getActiveTab();

  if (!isVS(tab?.url)) {
    showPanel('panel-not-vs');
    return;
  }

  showPanel('panel-main');

  try {
    const info = await msgTab(tab.id, { action: 'getBookInfo' });
    if (info) {
      bookTitle = info.title || 'VitalSource Book';
      el('book-title').textContent = bookTitle;
      el('book-meta').textContent =
        `Page ${info.currentPage ?? '?'} of ${info.totalPages ?? '?'}`;

      if (info.currentPage) el('start-page').value = info.currentPage;
      if (info.totalPages)  el('end-page').value   = info.totalPages;
    }
  } catch (_) {
    el('book-title').textContent = 'VitalSource Reader';
    el('book-meta').textContent  = 'Navigate to a book then reopen this popup';
  }
}

// ── PDF assembly (sequential queue) ──────────────────────────────────────────
function queueImage(dataUrl) {
  pageQueue.push(dataUrl);
  if (!processing) drainQueue();
}

async function drainQueue() {
  processing = true;
  while (pageQueue.length > 0) {
    await assembleOnePage(pageQueue.shift());
  }
  processing = false;
}

function assembleOnePage(dataUrl) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const w = img.naturalWidth;
      const h = img.naturalHeight;

      // Convert px to PDF points (72 pt/in, 96 px/in on screen)
      const PT = 72 / 96;
      const wPt = w * PT;
      const hPt = h * PT;

      if (!pdfDoc) {
        pdfDoc = new jsPDF({
          orientation: w >= h ? 'landscape' : 'portrait',
          unit: 'pt',
          format: [wPt, hPt],
        });
      } else {
        pdfDoc.addPage([wPt, hPt], w >= h ? 'landscape' : 'portrait');
      }

      pdfDoc.addImage(dataUrl, 'JPEG', 0, 0, wPt, hPt, undefined, 'FAST');
      resolve();
    };
    img.onerror = () => resolve(); // skip broken image, keep going
    img.src = dataUrl;
  });
}

function waitForQueueDrain() {
  return new Promise((resolve) => {
    const check = setInterval(() => {
      if (!processing && pageQueue.length === 0) {
        clearInterval(check);
        resolve();
      }
    }, 150);
  });
}

// ── Capture control ───────────────────────────────────────────────────────────
async function startCapture() {
  const tab = await getActiveTab();

  const startPage = parseInt(el('start-page').value, 10);
  const endPage   = parseInt(el('end-page').value,   10);
  const delayMs   = parseInt(el('delay-slider').value, 10);
  const crop      = el('crop-toggle').checked;

  if (!startPage || !endPage || startPage > endPage || startPage < 1) {
    alert('Please enter a valid page range (From ≤ To, both ≥ 1).');
    return;
  }

  const count = endPage - startPage + 1;
  if (count > 500 && !confirm(`Capturing ${count} pages will take a while. Continue?`)) return;

  // Reset state
  pdfDoc     = null;
  pageQueue  = [];
  processing = false;
  isCapturing = true;

  el('btn-start').hidden = true;
  el('btn-stop').hidden  = false;
  el('capture-progress').hidden = false;
  el('capture-done').hidden     = true;
  updateProgress(0, count);

  // Open port to background (keeps service worker alive)
  port = chrome.runtime.connect({ name: 'vs-pdf-session' });
  port.onMessage.addListener(onPortMessage);
  port.onDisconnect.addListener(() => {
    if (isCapturing) showError('Background worker disconnected. Please try again.');
  });

  port.postMessage({
    action: 'startCapture',
    tabId: tab.id,
    windowId: tab.windowId,
    startPage,
    endPage,
    delayMs,
    cropToContent: crop,
  });
}

function stopCapture() {
  if (port) port.postMessage({ action: 'cancelCapture' });
}

// ── Port message handler ──────────────────────────────────────────────────────
async function onPortMessage(msg) {
  switch (msg.action) {
    case 'progress':
      updateProgress(msg.current, msg.total);
      el('status-line').textContent = `Capturing page ${msg.page}…`;
      break;

    case 'image':
      queueImage(msg.dataUrl);
      break;

    case 'status':
      el('status-line').textContent = msg.message;
      break;

    case 'complete':
      await onComplete(msg.total);
      break;

    case 'cancelled':
      onCancelled();
      break;

    case 'error':
      showError(msg.message);
      break;
  }
}

async function onComplete(total) {
  isCapturing = false;
  el('status-line').textContent = 'Finalising PDF…';

  await waitForQueueDrain();

  el('btn-stop').hidden         = true;
  el('capture-progress').hidden = true;
  el('capture-done').hidden     = false;
  el('done-count').textContent  = String(total);

  if (port) { port.disconnect(); port = null; }
}

function onCancelled() {
  isCapturing = false;
  el('btn-start').hidden        = false;
  el('btn-stop').hidden         = true;
  el('capture-progress').hidden = true;
  el('status-line').textContent = '';
  if (port) { port.disconnect(); port = null; }
}

// ── Save PDF ──────────────────────────────────────────────────────────────────
async function savePDF() {
  if (!pdfDoc) { alert('No pages assembled yet.'); return; }

  await waitForQueueDrain();

  const safe = bookTitle.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').substring(0, 100);
  pdfDoc.save(`${safe}.pdf`);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function updateProgress(current, total) {
  const pct = total > 0 ? (current / total) * 100 : 0;
  el('progress-fill').style.width = `${pct.toFixed(1)}%`;
  el('progress-label').textContent = `${current} / ${total} pages`;
}

function showError(msg) {
  isCapturing = false;
  el('error-msg').textContent = msg;
  showPanel('panel-error');
  if (port) { port.disconnect(); port = null; }
}

function reset() {
  pdfDoc      = null;
  pageQueue   = [];
  processing  = false;
  isCapturing = false;
  el('btn-start').hidden        = false;
  el('btn-stop').hidden         = true;
  el('capture-progress').hidden = true;
  el('capture-done').hidden     = true;
  init();
}

// ── Event wiring ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  init();

  el('btn-start').addEventListener('click', startCapture);
  el('btn-stop').addEventListener('click', stopCapture);
  el('btn-save').addEventListener('click', savePDF);
  el('btn-restart').addEventListener('click', reset);
  el('btn-back').addEventListener('click', () => { showPanel('panel-main'); });

  el('delay-slider').addEventListener('input', (e) => {
    const s = parseInt(e.target.value, 10) / 1000;
    el('delay-label').textContent = `${s.toFixed(1)} s`;
  });
});
