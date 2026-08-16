(async function () {
  // ---- Messenger Marketplace inbox cleanup script ----
  // Run this on https://www.messenger.com/marketplace/ (the Marketplace inbox LIST view).
  // Step 1: scrolls the whole list to count every conversation and reports the total.
  // Step 2: repeatedly takes the top conversation, leaves the group (if that option
  //         exists), then deletes the chat, and moves to the next one — fully automatic,
  //         no further input needed — until the inbox is empty.
  // To stop early at any point, run:  window.__stopMarketplaceCleanup = true

  window.__stopMarketplaceCleanup = false;

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
  function jitter(min, max) {
    return min + Math.random() * (max - min);
  }

  function getListContainer() {
    return Array.from(document.querySelectorAll("div")).find((e) => {
      const s = getComputedStyle(e);
      return (
        (s.overflowY === "auto" || s.overflowY === "scroll") &&
        e.scrollHeight > e.clientHeight + 50
      );
    });
  }

  function getRowButtons(container) {
    return Array.from(
      container.querySelectorAll('[aria-label^="More options for"]')
    );
  }

  function getOpenMenuItems() {
    return Array.from(document.querySelectorAll('[role="menuitem"]'));
  }

  async function clickMenuItemStartingWith(text) {
    for (let i = 0; i < 15; i++) {
      const items = getOpenMenuItems();
      const item = items.find(
        (el) => el.innerText && el.innerText.trim().startsWith(text)
      );
      if (item) {
        item.click();
        return true;
      }
      await sleep(50);
    }
    return false;
  }

  async function menuHasItemStartingWith(text) {
    await sleep(100);
    const items = getOpenMenuItems();
    return items.some(
      (el) => el.innerText && el.innerText.trim().startsWith(text)
    );
  }

  async function clickDialogButtonExact(text) {
    for (let attempt = 0; attempt < 25; attempt++) {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog) {
        const buttons = Array.from(
          dialog.querySelectorAll('[role="button"], button')
        );
        const btn = buttons.find(
          (b) => b.innerText && b.innerText.trim() === text
        );
        if (btn) {
          btn.click();
          return true;
        }
      }
      await sleep(80);
    }
    return false;
  }

  async function waitForDialogToClose() {
    for (let i = 0; i < 25; i++) {
      if (!document.querySelector('[role="dialog"]')) return true;
      await sleep(80);
    }
    return false;
  }

  function pressEscape() {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })
    );
  }

  async function countAllConversations(container) {
    const seen = new Set();
    container.scrollTop = 0;
    await sleep(200);
    getRowButtons(container).forEach((b) => seen.add(b.getAttribute("aria-label")));

    let lastScrollTop = -1;
    let stableRounds = 0;
    let iterations = 0;
    while (stableRounds < 4 && iterations < 500) {
      container.scrollTop += 400;
      await sleep(120);
      getRowButtons(container).forEach((b) => seen.add(b.getAttribute("aria-label")));
      if (container.scrollTop === lastScrollTop) {
        stableRounds++;
      } else {
        stableRounds = 0;
      }
      lastScrollTop = container.scrollTop;
      iterations++;
    }
    container.scrollTop = 0;
    await sleep(200);
    return seen.size;
  }

  let container = getListContainer();
  if (!container) {
    console.error(
      "Could not find the Marketplace chat list. Make sure you're on messenger.com/marketplace/ with the inbox list visible."
    );
    return;
  }

  console.log("Counting conversations, please wait...");
  const initialCount = await countAllConversations(container);
  console.log(`Found ${initialCount} Marketplace conversations. Starting cleanup automatically...`);

  let deletedCount = 0;
  const deletedTitles = [];
  const skipped = [];
  let stagnantEmptyRounds = 0;
  let lastTitleSeen = null;
  let sameTitleRepeats = 0;
  let totalIterations = 0;
  const MAX_ITERATIONS = 400; // safety cap, well above the known ~87 chats

  console.log("Starting Marketplace cleanup...");

  while (totalIterations < MAX_ITERATIONS) {
    if (window.__stopMarketplaceCleanup) {
      console.log("Stopped by user (window.__stopMarketplaceCleanup = true).");
      break;
    }
    totalIterations++;

    container = getListContainer();
    if (!container) {
      console.warn("Lost reference to chat list, retrying...");
      await sleep(500);
      continue;
    }

    container.scrollTop = 0;
    await sleep(100);

    let rows = getRowButtons(container);

    if (rows.length === 0) {
      // Try nudging scroll to force any lazy content to render, then re-check.
      container.scrollTop = container.scrollHeight;
      await sleep(400);
      container.scrollTop = 0;
      await sleep(250);
      rows = getRowButtons(container);
      if (rows.length === 0) {
        stagnantEmptyRounds++;
        console.log(
          `Inbox appears empty (check ${stagnantEmptyRounds}/3)...`
        );
        if (stagnantEmptyRounds >= 3) {
          console.log("Marketplace inbox is empty. Done.");
          break;
        }
        continue;
      }
    }
    stagnantEmptyRounds = 0;

    const rowBtn = rows[0];
    const title = (rowBtn.getAttribute("aria-label") || "")
      .replace("More options for", "")
      .trim();

    // Safety: bail out on a single stuck conversation instead of looping forever.
    if (title === lastTitleSeen) {
      sameTitleRepeats++;
    } else {
      sameTitleRepeats = 0;
      lastTitleSeen = title;
    }
    if (sameTitleRepeats >= 4) {
      console.warn(
        `Skipping "${title}" after repeated failures to delete it.`
      );
      skipped.push(title);
      sameTitleRepeats = 0;
      lastTitleSeen = null;
      pressEscape();
      await sleep(500);
      continue;
    }

    console.log(`Processing: ${title}`);
    rowBtn.click();
    await sleep(jitter(120, 220));

    const hasLeave = await menuHasItemStartingWith("Leave group");

    if (hasLeave) {
      const clickedLeave = await clickMenuItemStartingWith("Leave group");
      if (clickedLeave) {
        const confirmedLeave = await clickDialogButtonExact("Leave group");
        if (confirmedLeave) {
          await waitForDialogToClose();
        } else {
          console.warn(`Could not confirm "Leave group" for: ${title}`);
          pressEscape();
        }
      }
      await sleep(jitter(150, 250));

      // Re-open the options menu on the same row to proceed to delete.
      container = getListContainer();
      container.scrollTop = 0;
      await sleep(100);
      const rowsAfterLeave = getRowButtons(container);
      const rowAgain =
        rowsAfterLeave.find((r) =>
          (r.getAttribute("aria-label") || "").includes(title)
        ) || rowsAfterLeave[0];
      if (rowAgain) {
        rowAgain.click();
        await sleep(jitter(120, 220));
      } else {
        console.warn(`Row disappeared before delete step: ${title}`);
        continue;
      }
    }

    const clickedDelete = await clickMenuItemStartingWith("Delete chat");
    if (clickedDelete) {
      const confirmedDelete = await clickDialogButtonExact("Delete chat");
      if (confirmedDelete) {
        await waitForDialogToClose();
        deletedCount++;
        deletedTitles.push(title);
        console.log(`Deleted (${deletedCount}): ${title}`);
      } else {
        console.warn(`Could not confirm delete for: ${title}`);
        pressEscape();
      }
    } else {
      console.warn(`"Delete chat" option not found for: ${title}`);
      pressEscape();
    }

    await sleep(jitter(250, 500)); // brief pacing between conversations
  }

  if (totalIterations >= MAX_ITERATIONS) {
    console.warn("Hit the safety iteration cap — stopping. Re-run the script to continue.");
  }

  console.log("---- Marketplace cleanup summary ----");
  console.log(`Found at start: ${initialCount}`);
  console.log(`Deleted: ${deletedCount}`);
  if (skipped.length) {
    console.log(`Skipped (repeated failures): ${skipped.length}`, skipped);
  }
  console.log("Deleted titles:", deletedTitles);
})();