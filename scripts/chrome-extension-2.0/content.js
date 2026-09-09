'use strict';

// Confirmed working selectors from live DOM inspection (Sept 2026)
const PAGE_INPUT_SELECTORS = [
  'input[type="text"]',               // Only text input on the page — confirmed
  'input[aria-label*="page" i]',
  'nav input[type="number"]',
  '.toolbar input[type="text"]',
];

const NEXT_SELECTORS = [
  'button[aria-label="Next"]',        // Confirmed working
  'button[aria-label="Next Page"]',
  'button[aria-label="Next page"]',
  '[data-testid="next-page-button"]',
  'button[aria-label*="next" i]:not([aria-label*="chapter" i])',
];

const PREV_SELECTORS = [
  'button[aria-label="Previous"]',    // Confirmed working
  'button[aria-label="Previous Page"]',
  'button[aria-label="Previous page"]',
  '[data-testid="prev-page-button"]',
  'button[aria-label*="prev" i]',
];

const CONTENT_IFRAME_SELECTORS = [
  'iframe[title="Document reading pane"]',  // Confirmed present
  'iframe#content',
  'iframe#book-content',
  'iframe.epub-container',
  'iframe[src*="epub"]',
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
  const btn = find(NEXT_SELECTORS);
  if (btn && !btn.disabled) {
    btn.click();
    return 'button';
  }

  // Fallback: ArrowRight in iframe or document
  const iframe = find(CONTENT_IFRAME_SELECTORS);
  if (iframe) {
    iframe.focus();
    iframe.contentDocument?.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', keyCode: 39, bubbles: true, cancelable: true })
    );
  }
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

      case 'navigateToPageLabel': {
        const label = String(msg.label || '').trim();

        // Primary: TOC button with aria-label ending in ", page <label>"
        // Confirmed working for both Roman (ii, iii…) and numeric (1, 2…) labels
        const tocBtn = document.querySelector(`button[aria-label$=", page ${label}"]`);
        if (tocBtn) {
          tocBtn.click();
          sendResponse({ success: true, method: 'toc-button' });
          break;
        }

        // Fallback: page number input (React-compatible)
        const input = find(PAGE_INPUT_SELECTORS);
        if (input) {
          input.focus();
          const nativeSetter = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype, 'value'
          )?.set;
          if (nativeSetter) nativeSetter.call(input, label);
          else input.value = label;

          ['input', 'change'].forEach((t) =>
            input.dispatchEvent(new Event(t, { bubbles: true }))
          );
          ['keydown', 'keypress', 'keyup'].forEach((t) =>
            input.dispatchEvent(
              new KeyboardEvent(t, { key: 'Enter', keyCode: 13, bubbles: true })
            )
          );
          sendResponse({ success: true, method: 'input' });
          break;
        }

        sendResponse({ success: false, method: 'none' });
        break;
      }

      default:
        sendResponse({ error: 'unknown action' });
    }
  })();
  return true;
});
