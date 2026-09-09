'use strict';

const NEXT_SELECTORS = [
  // VitalSource web reader — current DOM (2024-2025)
  'button[aria-label="Next Page"]',
  'button[aria-label="Next page"]',
  'button[aria-label="next page"]',
  'button[aria-label="Next"]',
  '[data-testid="next-page-button"]',
  '[data-testid="pagination-next"]',
  // Generic fallbacks
  '.next-page-button',
  'button[title="Next page"]',
  'button[title="Next Page"]',
  'button[aria-label*="next" i]:not([aria-label*="chapter" i])',
];

const PREV_SELECTORS = [
  'button[aria-label="Previous Page"]',
  'button[aria-label="Previous page"]',
  'button[aria-label="Prev"]',
  '[data-testid="prev-page-button"]',
  '[data-testid="pagination-prev"]',
  '.prev-page-button',
  'button[aria-label*="prev" i]',
];

const CONTENT_IFRAME_SELECTORS = [
  'iframe#content',
  'iframe#book-content',
  'iframe#contentframe',
  'iframe.epub-container',
  'iframe[src*="epub"]',
  'iframe[title*="book" i]',
  '#reader iframe',
  '.reader-container iframe',
  'iframe',
];

function find(selectors) {
  for (const sel of selectors) {
    try {
      const el = document.querySelector(sel);
      if (el) return el;
    } catch (_) {}
  }
  return null;
}

function getContentArea() {
  const iframe = find(CONTENT_IFRAME_SELECTORS);
  if (iframe) {
    const r = iframe.getBoundingClientRect();
    if (r.width > 100 && r.height > 100) {
      return { x: Math.round(r.left), y: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) };
    }
  }
  return { x: 0, y: 60, width: window.innerWidth, height: window.innerHeight - 60 };
}

function getBookTitle() {
  const og = document.querySelector('meta[property="og:title"]');
  if (og?.content) return og.content;
  return (document.title || '')
    .replace(/\s*[-|]?\s*(VitalSource|Chegg|Bookshelf).*$/i, '')
    .trim() || 'VitalSource Book';
}

function clickNextPage() {
  // 1. Try button
  const btn = find(NEXT_SELECTORS);
  if (btn && !btn.disabled) {
    btn.click();
    return 'button';
  }

  // 2. Focus the content area and send ArrowRight
  const iframe = find(CONTENT_IFRAME_SELECTORS);
  if (iframe) {
    iframe.focus();
    iframe.contentDocument?.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', keyCode: 39, bubbles: true, cancelable: true })
    );
  }

  // 3. Also send to main document
  document.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'ArrowRight', keyCode: 39, bubbles: true, cancelable: true })
  );
  document.dispatchEvent(
    new KeyboardEvent('keyup', { key: 'ArrowRight', keyCode: 39, bubbles: true })
  );

  return 'keyboard';
}

// ── Message handler ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    switch (msg.action) {

      case 'ping':
        sendResponse({ ok: true });
        break;

      case 'getUrl':
        sendResponse({ url: window.location.href });
        break;

      case 'getBookInfo':
        sendResponse({
          title:       getBookTitle(),
          url:         window.location.href,
          contentArea: getContentArea(),
        });
        break;

      case 'nextPage': {
        const method = clickNextPage();
        sendResponse({ method });
        break;
      }

      default:
        sendResponse({ error: 'unknown action' });
    }
  })();
  return true;
});
