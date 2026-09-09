'use strict';

const { jsPDF } = window.jspdf;

// ── State ─────────────────────────────────────────────────────────────────────
let port        = null;
let images      = [];
let isCapturing = false;
let bookTitle   = 'VitalSource Book';

// ── DOM ───────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ── Tab helpers ───────────────────────────────────────────────────────────────
function msgTab(tabId, msg) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, msg, (r) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(r);
    });
  });
}

async function getVSTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && (tab.url?.includes('vitalsource.com') || tab.url?.includes('chegg.com'))) {
    return tab;
  }
  return null;
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  const tab = await getVSTab();

  if (!tab) {
    $('not-vs').hidden = false;
    $('main').hidden   = true;
    return;
  }

  $('not-vs').hidden = true;
  $('main').hidden   = false;

  try {
    const info = await msgTab(tab.id, { action: 'getBookInfo' });
    bookTitle = info?.title || 'VitalSource Book';
    $('book-title').textContent = bookTitle;
  } catch (_) {
    $('book-title').textContent = 'VitalSource Reader';
  }
}

// ── Start capture ─────────────────────────────────────────────────────────────
async function startCapture() {
  const tab = await getVSTab();
  if (!tab) { alert('Please open a VitalSource book first.'); return; }

  const countVal = $('page-count').value.trim();
  const count    = countVal ? parseInt(countVal, 10) : 0; // 0 = unlimited
  const delayMs  = Math.max(500, parseInt($('delay-input').value, 10) || 1500);
  const qual     = $('quality-select').value;
  const crop     = $('crop-toggle').checked;

  if (countVal && (isNaN(count) || count < 1)) {
    alert('Please enter a valid page count (or leave blank to scan until stopped).');
    return;
  }

  if (count > 1000 && !confirm(`Scanning ${count} pages may take a long time. Continue?`)) return;

  let format = 'jpeg', quality = 92;
  if (qual === 'png')       { format = 'png'; quality = 100; }
  else if (qual === 'jpeg-70') { quality = 70; }

  images      = [];
  isCapturing = true;
  updateThumbGrid();
  setButtons('scanning');
  $('scan-progress').hidden = false;
  updateProgress(0, count);

  port = chrome.runtime.connect({ name: 'vs-pdf-session' });
  port.onMessage.addListener(onPortMsg);
  port.onDisconnect.addListener(() => {
    if (isCapturing) {
      isCapturing = false;
      setButtons(images.length > 0 ? 'done' : 'idle');
    }
  });

  port.postMessage({
    action: 'startCapture',
    tabId:    tab.id,
    windowId: tab.windowId,
    count,        // 0 = capture until cancelled
    delayMs,
    format,
    quality,
    cropToContent: crop,
  });
}

// ── Port messages ─────────────────────────────────────────────────────────────
function onPortMsg(msg) {
  switch (msg.action) {

    case 'progress':
      updateProgress(msg.current, msg.total);
      break;

    case 'image':
      images.push({ dataUrl: msg.dataUrl, thumb: msg.thumb });
      addThumb(msg.thumb, images.length - 1);
      $('count-line').textContent = `${images.length} pages captured`;
      break;

    case 'complete':
    case 'cancelled':
      isCapturing = false;
      setButtons(images.length > 0 ? 'done' : 'idle');
      $('scan-progress').hidden = true;
      port?.disconnect();
      port = null;
      break;

    case 'error':
      isCapturing = false;
      setButtons(images.length > 0 ? 'done' : 'idle');
      $('scan-progress').hidden = true;
      alert('Capture error: ' + msg.message);
      port?.disconnect();
      port = null;
      break;
  }
}

// ── Controls ──────────────────────────────────────────────────────────────────
function stopCapture() { port?.postMessage({ action: 'cancelCapture' }); }

function clearAll() {
  images = [];
  updateThumbGrid();
  setButtons('idle');
  $('scan-progress').hidden = true;
  updateProgress(0, 0);
}

// ── PDF generation ────────────────────────────────────────────────────────────
async function createPDF() {
  if (images.length === 0) return;

  $('btn-pdf').textContent = '⏳ Building…';
  $('btn-pdf').disabled    = true;

  const PT  = 72 / 96;
  let   pdf = null;

  for (const { dataUrl } of images) {
    await new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const w      = img.naturalWidth  * PT;
        const h      = img.naturalHeight * PT;
        const orient = img.naturalWidth >= img.naturalHeight ? 'landscape' : 'portrait';
        if (!pdf) {
          pdf = new jsPDF({ orientation: orient, unit: 'pt', format: [w, h] });
        } else {
          pdf.addPage([w, h], orient);
        }
        const imgType = dataUrl.startsWith('data:image/png') ? 'PNG' : 'JPEG';
        pdf.addImage(dataUrl, imgType, 0, 0, w, h, undefined, 'FAST');
        resolve();
      };
      img.onerror = () => resolve();
      img.src = dataUrl;
    });
  }

  if (pdf) {
    const safe = bookTitle.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').substring(0, 100);
    pdf.save(`${safe}.pdf`);
  }

  $('btn-pdf').textContent = '📄 Create PDF';
  $('btn-pdf').disabled    = false;
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function setButtons(state) {
  const scan  = $('btn-scan');
  const stop  = $('btn-stop');
  const clear = $('btn-clear');
  const pdf   = $('btn-pdf');
  switch (state) {
    case 'scanning':
      scan.disabled  = true;
      stop.disabled  = false;
      clear.disabled = true;
      pdf.disabled   = true;
      break;
    case 'done':
      scan.disabled  = false;
      stop.disabled  = true;
      clear.disabled = false;
      pdf.disabled   = images.length === 0;
      break;
    default:
      scan.disabled  = false;
      stop.disabled  = true;
      clear.disabled = images.length === 0;
      pdf.disabled   = images.length === 0;
  }
}

function updateProgress(current, total) {
  if (total > 0) {
    const pct = (current / total) * 100;
    $('progress-fill').style.width = `${pct.toFixed(1)}%`;
    $('progress-text').textContent = `${current} / ${total} pages`;
  } else {
    $('progress-fill').style.width = '0%';
    $('progress-text').textContent = current > 0 ? `${current} pages captured` : '0 pages';
  }
}

function updateThumbGrid() {
  const grid = $('thumb-grid');
  grid.innerHTML = '';
  const has = images.length > 0;
  grid.hidden               = !has;
  $('preview-label').hidden = !has;
  $('count-line').hidden    = !has;
  if (has) {
    $('count-line').textContent = `${images.length} pages captured`;
    images.forEach((img, i) => addThumb(img.thumb, i));
  }
}

function addThumb(thumbDataUrl, index) {
  const grid = $('thumb-grid');
  grid.hidden               = false;
  $('preview-label').hidden = false;
  $('count-line').hidden    = false;

  const div = document.createElement('div');
  div.className = 'thumb-item';
  div.title     = `Page ${index + 1}`;

  if (thumbDataUrl) {
    const img = document.createElement('img');
    img.src = thumbDataUrl;
    img.alt = `Page ${index + 1}`;
    div.appendChild(img);
  } else {
    div.classList.add('pending');
    div.textContent = index + 1;
  }

  grid.appendChild(div);
  grid.scrollTop = grid.scrollHeight;
}

// ── Wiring ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  init();

  $('btn-scan').addEventListener('click',  startCapture);
  $('btn-stop').addEventListener('click',  stopCapture);
  $('btn-clear').addEventListener('click', clearAll);
  $('btn-pdf').addEventListener('click',   createPDF);

  setButtons('idle');
});

chrome.tabs.onActivated.addListener(() => { if (!isCapturing) init(); });
chrome.tabs.onUpdated.addListener((_id, info) => {
  if (info.status === 'complete' && !isCapturing) init();
});
