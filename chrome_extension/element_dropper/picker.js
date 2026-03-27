(function () {
  if (window.__elementDropperApi) {
    window.__elementDropperStartPick = window.__elementDropperApi.startPick;
    return;
  }

  let active = false;
  let currentSlot = null;
  let highlighted = null;
  let tip = null;
  let oldCursor = "";

  function cleanup() {
    if (!active) {
      return;
    }
    active = false;
    currentSlot = null;

    document.removeEventListener("mousemove", onMove, true);
    document.removeEventListener("mousedown", onMouseDown, true);
    document.removeEventListener("click", onClickBlock, true);
    document.removeEventListener("keydown", onKeydown, true);

    document.documentElement.style.cursor = oldCursor;
    document.body.style.cursor = oldCursor;

    if (highlighted) {
      highlighted.style.outline = "";
      highlighted = null;
    }
    if (tip) {
      tip.remove();
      tip = null;
    }
  }

  function cssEscape(value) {
    if (window.CSS && window.CSS.escape) {
      return window.CSS.escape(value);
    }
    const text = String(value || "");
    let out = "";
    for (let i = 0; i < text.length; i += 1) {
      const ch = text[i];
      const code = ch.charCodeAt(0);
      const isUpper = code >= 65 && code <= 90;
      const isLower = code >= 97 && code <= 122;
      const isDigit = code >= 48 && code <= 57;
      if (isUpper || isLower || isDigit || ch === "_" || ch === "-") {
        out += ch;
      } else {
        out += `\\${ch}`;
      }
    }
    return out;
  }

  function buildSelector(el) {
    if (el.id) {
      return `#${cssEscape(el.id)}`;
    }

    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE && node.tagName.toLowerCase() !== "html") {
      const tag = node.tagName.toLowerCase();
      let index = 1;
      let sibling = node;
      while ((sibling = sibling.previousElementSibling)) {
        if (sibling.tagName.toLowerCase() === tag) {
          index += 1;
        }
      }
      parts.unshift(`${tag}:nth-of-type(${index})`);
      node = node.parentElement;
    }
    return parts.join(" > ");
  }

  function ensureTip() {
    if (tip) {
      return;
    }
    tip = document.createElement("div");
    tip.style.position = "fixed";
    tip.style.zIndex = "2147483647";
    tip.style.background = "rgba(26, 33, 61, 0.95)";
    tip.style.color = "white";
    tip.style.padding = "8px 10px";
    tip.style.borderRadius = "6px";
    tip.style.fontSize = "12px";
    tip.style.pointerEvents = "none";
    tip.style.maxWidth = "320px";
    tip.style.lineHeight = "1.3";
    document.documentElement.appendChild(tip);
  }

  function onMove(event) {
    if (!active) {
      return;
    }
    ensureTip();

    if (highlighted && highlighted !== event.target) {
      highlighted.style.outline = "";
    }
    highlighted = event.target;
    highlighted.style.outline = "2px solid #00b3ff";

    const preview = (highlighted.innerText || highlighted.textContent || "").trim().slice(0, 80);
    tip.textContent = `Picking ${currentSlot} | ${highlighted.tagName.toLowerCase()} | ${preview || "(no text)"}`;
    tip.style.left = `${Math.min(window.innerWidth - 330, event.clientX + 12)}px`;
    tip.style.top = `${Math.min(window.innerHeight - 40, event.clientY + 12)}px`;
  }

  function onMouseDown(event) {
    if (!active) {
      return;
    }
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const el = event.target;
    const selector = buildSelector(el);
    const previewText = (el.innerText || el.textContent || "").trim().slice(0, 200);

    const selectedSlot = currentSlot;
    chrome.runtime.sendMessage(
      {
        type: "picked",
        slot: selectedSlot,
        selector,
        previewText
      },
      (response) => {
        const runtimeError = chrome.runtime.lastError;
        if (runtimeError) {
          ensureTip();
          tip.textContent = `Pick failed: ${runtimeError.message || "background unavailable"}. Try again.`;
          tip.style.left = "16px";
          tip.style.top = "16px";
          return;
        }

        if (!response || !response.ok) {
          ensureTip();
          const msg = (response && response.error) ? response.error : "Selection was not saved. Try again.";
          tip.textContent = `Pick failed: ${msg}`;
          tip.style.left = "16px";
          tip.style.top = "16px";
          return;
        }

        ensureTip();
        tip.textContent = `Saved ${selectedSlot}.`;
        tip.style.left = "16px";
        tip.style.top = "16px";
        setTimeout(() => {
          cleanup();
        }, 250);
      }
    );
  }

  function onClickBlock(event) {
    if (!active) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
  }

  function onKeydown(event) {
    if (event.key === "Escape") {
      cleanup();
    }
  }

  function startPick(slot) {
    cleanup();
    active = true;
    currentSlot = slot;
    oldCursor = document.documentElement.style.cursor || "";
    document.documentElement.style.cursor = "crosshair";
    document.body.style.cursor = "crosshair";
    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("mousedown", onMouseDown, true);
    document.addEventListener("click", onClickBlock, true);
    document.addEventListener("keydown", onKeydown, true);
    ensureTip();
    tip.textContent = `Picking ${currentSlot}. Move mouse and click element. ESC to cancel.`;
    tip.style.left = "16px";
    tip.style.top = "16px";
  }

  window.__elementDropperApi = { startPick };
  window.__elementDropperStartPick = startPick;

  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "startPick") {
      startPick(message.slot);
    }
  });
})();
