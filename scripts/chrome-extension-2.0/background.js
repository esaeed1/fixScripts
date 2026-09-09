'use strict';

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(console.error);

let activePort = null;
let session    = null;

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'vs-pdf-session') return;
  activePort = port;

  port.onDisconnect.addListener(() => {
    activePort = null;
    if (session) session.cancelled = true;
  });

  port.onMessage.addListener(async (msg) => {
    if (msg.action === 'startCapture') {
      await runCapture(port, msg);
    } else if (msg.action === 'cancelCapture') {
      if (session) session.cancelled = true;
      port.postMessage({ action: 'cancelled' });
    }
  });
});

// ── Tab messaging ─────────────────────────────────────────────────────────────

function sendToTab(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (res) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(res);
    });
  });
}

// Inject content.js if the tab doesn't respond to ping
async function ensureContentScript(tabId) {
  try {
    await sendToTab(tabId, { action: 'ping' });
    return true;
  } catch (_) {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
      await delay(400);
      return true;
    } catch (err) {
      return false;
    }
  }
}

// ── Screenshot + crop ─────────────────────────────────────────────────────────

function captureTab(windowId, format, quality) {
  const opts = format === 'png'
    ? { format: 'png' }
    : { format: 'jpeg', quality: quality || 92 };
  return new Promise((resolve, reject) => {
    chrome.tabs.captureVisibleTab(windowId, opts, (dataUrl) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(dataUrl);
    });
  });
}

async function cropToRect(dataUrl, rect) {
  if (!rect || rect.width <= 10 || rect.height <= 10) return dataUrl;
  try {
    const blob   = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);
    const dpr    = rect.devicePixelRatio || 1;
    const canvas = new OffscreenCanvas(
      Math.round(rect.width  * dpr),
      Math.round(rect.height * dpr)
    );
    canvas.getContext('2d').drawImage(
      bitmap,
      -Math.round(rect.x * dpr),
      -Math.round(rect.y * dpr)
    );
    const outBlob = await canvas.convertToBlob({
      type:    dataUrl.startsWith('data:image/png') ? 'image/png' : 'image/jpeg',
      quality: 0.92,
    });
    return new Promise((r) => {
      const reader = new FileReader();
      reader.onload = () => r(reader.result);
      reader.readAsDataURL(outBlob);
    });
  } catch (err) {
    console.warn('[VS-PDF] crop failed:', err.message);
    return dataUrl;
  }
}

async function makeThumbnail(dataUrl, thumbW = 90) {
  try {
    const blob   = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);
    const h      = Math.round(thumbW * (bitmap.height / bitmap.width));
    const canvas = new OffscreenCanvas(thumbW, h);
    canvas.getContext('2d').drawImage(bitmap, 0, 0, thumbW, h);
    const outBlob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.6 });
    return new Promise((r) => {
      const reader = new FileReader();
      reader.onload = () => r(reader.result);
      reader.readAsDataURL(outBlob);
    });
  } catch (_) { return null; }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function delay(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function waitForUrlChange(tabId, originalUrl, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await delay(250);
    try {
      const res = await sendToTab(tabId, { action: 'getUrl' });
      if (res?.url && res.url !== originalUrl) return true;
    } catch (_) {}
  }
  return false;
}

// ── Capture loop ──────────────────────────────────────────────────────────────
//
// count = 0 means capture until cancelled (unlimited)
// Starts from the reader's current position — user navigates there manually

async function runCapture(port, { tabId, windowId, count, delayMs, format, quality, cropToContent }) {
  session = { cancelled: false };
  const waitMs   = Math.max(800, Math.min(8000, delayMs || 1500));
  const unlimited = count === 0;
  let   captured  = 0;

  // Ensure content script is injected
  const ok = await ensureContentScript(tabId);
  if (!ok) {
    port.postMessage({ action: 'error', message: 'Could not connect to VitalSource tab. Please refresh the page and try again.' });
    session = null;
    return;
  }

  // Get content area for cropping
  let contentArea = null;
  if (cropToContent) {
    try {
      const info = await sendToTab(tabId, { action: 'getBookInfo' });
      if (info?.contentArea) {
        const [dprRes] = await chrome.scripting.executeScript({
          target: { tabId },
          func:   () => window.devicePixelRatio || 1,
        });
        contentArea = { ...info.contentArea, devicePixelRatio: dprRes?.result || 1 };
      }
    } catch (_) {}
  }

  port.postMessage({ action: 'progress', current: 0, total: count });

  try {
    while (true) {
      if (session.cancelled) {
        port.postMessage({ action: 'cancelled' });
        return;
      }
      if (!unlimited && captured >= count) break;

      captured++;
      port.postMessage({ action: 'progress', current: captured, total: count });

      // Screenshot current page
      let dataUrl;
      try {
        dataUrl = await captureTab(windowId, format, quality);
        if (contentArea) dataUrl = await cropToRect(dataUrl, contentArea);
      } catch (err) {
        port.postMessage({ action: 'error', message: `Screenshot failed (page ${captured}): ${err.message}` });
        return;
      }

      const thumb = await makeThumbnail(dataUrl);
      port.postMessage({ action: 'image', dataUrl, thumb, index: captured - 1 });

      // Check if we're done
      if (!unlimited && captured >= count) break;
      if (session.cancelled) {
        port.postMessage({ action: 'cancelled' });
        return;
      }

      // Navigate to next page and wait for load
      let urlBefore;
      try { urlBefore = (await sendToTab(tabId, { action: 'getUrl' }))?.url; } catch (_) {}

      try { await sendToTab(tabId, { action: 'nextPage' }); } catch (_) {}

      if (urlBefore) {
        const changed = await waitForUrlChange(tabId, urlBefore, waitMs * 1.5);
        await delay(changed ? Math.min(waitMs, 1200) : waitMs);
      } else {
        await delay(waitMs);
      }
    }

    port.postMessage({ action: 'complete' });

  } catch (err) {
    port.postMessage({ action: 'error', message: err.message });
  } finally {
    session = null;
  }
}
