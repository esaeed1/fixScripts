'use strict';

// Open the side panel when the toolbar icon is clicked
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(console.error);

// Active port keeps service worker alive during capture
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

// ── Tab helpers ───────────────────────────────────────────────────────────────

function sendToTab(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (res) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(res);
    });
  });
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
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, -Math.round(rect.x * dpr), -Math.round(rect.y * dpr));
    const outBlob = await canvas.convertToBlob({
      type:    dataUrl.startsWith('data:image/png') ? 'image/png' : 'image/jpeg',
      quality: 0.92,
    });
    return new Promise(r => {
      const reader = new FileReader();
      reader.onload = () => r(reader.result);
      reader.readAsDataURL(outBlob);
    });
  } catch (err) {
    console.warn('[VS-PDF] crop failed:', err.message);
    return dataUrl;
  }
}

async function makeThumbnail(dataUrl, thumbWidth = 90) {
  try {
    const blob   = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);
    const ratio  = bitmap.height / bitmap.width;
    const canvas = new OffscreenCanvas(thumbWidth, Math.round(thumbWidth * ratio));
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const outBlob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.6 });
    return new Promise(r => {
      const reader = new FileReader();
      reader.onload = () => r(reader.result);
      reader.readAsDataURL(outBlob);
    });
  } catch (_) {
    return null;
  }
}

// ── Navigation helpers ────────────────────────────────────────────────────────

async function waitForUrlChange(tabId, originalUrl, timeoutMs = 7000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await delay(250);
    try {
      const res = await sendToTab(tabId, { action: 'getUrl' });
      if (res?.url && res.url !== originalUrl) return res.url;
    } catch (_) {}
  }
  return null; // timed out — proceed anyway
}

function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ── Main capture loop ─────────────────────────────────────────────────────────

async function runCapture(port, { tabId, windowId, pageCount, delayMs, format, quality, cropToContent }) {
  session = { cancelled: false };
  const waitMs = Math.max(800, Math.min(8000, delayMs || 1500));

  try {
    // Optionally get content area for cropping
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

    for (let i = 0; i < pageCount; i++) {
      if (session.cancelled) {
        port.postMessage({ action: 'cancelled' });
        return;
      }

      port.postMessage({ action: 'progress', current: i + 1, total: pageCount });

      // Capture
      let dataUrl;
      try {
        dataUrl = await captureTab(windowId, format, quality);
        if (cropToContent && contentArea) {
          dataUrl = await cropToRect(dataUrl, contentArea);
        }
      } catch (err) {
        port.postMessage({ action: 'error', message: `Screenshot failed on page ${i + 1}: ${err.message}` });
        return;
      }

      // Thumbnail
      const thumb = await makeThumbnail(dataUrl);

      // Send to side panel
      port.postMessage({ action: 'image', dataUrl, thumb, index: i });

      // Navigate to next page (skip after last)
      if (i < pageCount - 1) {
        let currentUrl;
        try {
          const urlRes = await sendToTab(tabId, { action: 'getUrl' });
          currentUrl = urlRes?.url;
        } catch (_) {}

        await sendToTab(tabId, { action: 'nextPage' });

        // Wait for URL change or fall back to fixed delay
        if (currentUrl) {
          const changed = await waitForUrlChange(tabId, currentUrl, waitMs);
          if (changed) {
            // Extra render time after URL change
            await delay(Math.min(waitMs, 1000));
          } else {
            await delay(waitMs);
          }
        } else {
          await delay(waitMs);
        }
      }
    }

    port.postMessage({ action: 'complete' });

  } catch (err) {
    port.postMessage({ action: 'error', message: err.message });
  } finally {
    session = null;
  }
}
