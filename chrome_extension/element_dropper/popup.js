const endpointInput = document.getElementById("endpoint");
const statusEl = document.getElementById("status");
const connectionEl = document.getElementById("connection");

function setStatus(text) {
  statusEl.textContent = text;
}

function setConnection(ok, text) {
  connectionEl.textContent = text;
  connectionEl.classList.remove("connection-ok", "connection-bad");
  if (ok === true) {
    connectionEl.classList.add("connection-ok");
  } else if (ok === false) {
    connectionEl.classList.add("connection-bad");
  }
}

function formatTime(timestamp) {
  return timestamp ? new Date(timestamp).toLocaleTimeString() : "-";
}

function formatPage(target, latest) {
  const pageTitle = latest && latest.pageTitle ? latest.pageTitle : (target && target.pageTitle ? target.pageTitle : "");
  const pageUrl = latest && latest.pageUrl ? latest.pageUrl : (target && target.pageUrl ? target.pageUrl : "");
  if (pageTitle && pageUrl) {
    return `${pageTitle} | ${pageUrl}`;
  }
  return pageTitle || pageUrl || "-";
}

function setSlotState(slot, state) {
  const target = state.targets[slot];
  const latest = state.latest[slot];
  const selectorEl = document.getElementById(`${slot}-selector`);
  const previewEl = document.getElementById(`${slot}-preview`);
  const valueEl = document.getElementById(`${slot}-value`);
  const updatedEl = document.getElementById(`${slot}-updated`);
  const pageEl = document.getElementById(`${slot}-page`);
  const pickButton = document.querySelector(`.pick-btn[data-slot="${slot}"]`);
  const repickButton = document.querySelector(`.repick-btn[data-slot="${slot}"]`);
  const testButton = document.querySelector(`.test-btn[data-slot="${slot}"]`);
  const clearButton = document.querySelector(`.clear-btn[data-slot="${slot}"]`);
  const locked = !!(target && target.selector);

  if (selectorEl) {
    selectorEl.textContent = `Selector: ${target && target.selector ? target.selector : "-"}`;
  }
  if (previewEl) {
    previewEl.textContent = `Preview: ${target && target.previewText ? target.previewText : "-"}`;
  }
  if (valueEl) {
    valueEl.textContent = `Value: ${latest && latest.text ? latest.text : "-"}`;
  }
  if (updatedEl) {
    updatedEl.textContent = `Updated: ${formatTime(latest && latest.updatedAt)}`;
  }
  if (pageEl) {
    pageEl.textContent = `Page: ${formatPage(target, latest)}`;
  }
  if (pickButton) {
    pickButton.disabled = locked;
    pickButton.title = locked ? "Clear this slot first to pick a new element." : "";
  }
  if (repickButton) {
    repickButton.disabled = !locked;
  }
  if (testButton) {
    testButton.disabled = !locked;
  }
  if (clearButton) {
    clearButton.disabled = !locked;
  }
}

function renderState(state) {
  endpointInput.value = state.endpoint || "";
  setSlotState("topstep", state);
  setSlotState("tradovate", state);
  
  // Show/hide action buttons section based on app activation signal
  const actionButtonsSection = document.getElementById("action-buttons-section");
  if (state.actionButtonsActive) {
    actionButtonsSection.style.display = "block";
    // Set state for action button slots
    setSlotState("buy-button", state);
    setSlotState("sell-button", state);
    setSlotState("close-button", state);
  } else {
    actionButtonsSection.style.display = "none";
  }

  const appConnection = state.appConnection || {};
  if (appConnection.ok === true) {
    setConnection(true, `App: connected | last push ${formatTime(appConnection.lastSuccessAt)}`);
  } else if (appConnection.ok === false) {
    setConnection(false, `App: unreachable | ${appConnection.lastError || "unknown error"}`);
  } else {
    setConnection(null, "App: not tested");
  }
  
  updateLiveTradesHub(state.liveTrades);
}

function updateLiveTradesHub(isEnabled) {
  const indicator = document.getElementById("hub-indicator");
  const label = document.getElementById("hub-label");
  
  if (isEnabled) {
    indicator.classList.add("active");
    label.textContent = "Live Trading: ON";
  } else {
    indicator.classList.remove("active");
    label.textContent = "Live Trading: OFF";
  }
}

async function sendMessage(message) {
  return chrome.runtime.sendMessage(message);
}

async function refresh() {
  const response = await sendMessage({ type: "getState" });
  if (response && response.ok) {
    renderState(response.state);
  } else {
    setStatus(response && response.error ? response.error : "Could not load state.");
  }
}

document.getElementById("save-endpoint").addEventListener("click", async () => {
  const endpoint = endpointInput.value.trim();
  const response = await sendMessage({ type: "setEndpoint", endpoint });
  if (response && response.ok) {
    setStatus("Endpoint saved.");
    renderState(response.state);
  } else {
    setStatus(response && response.error ? response.error : "Failed to save endpoint.");
  }
});

for (const button of document.querySelectorAll(".pick-btn")) {
  button.addEventListener("click", async () => {
    const slot = button.getAttribute("data-slot");
    const response = await sendMessage({ type: "beginPick", slot });
    if (response && response.ok) {
      setStatus(`Pick mode started for ${slot}. Click an element on the page.`);
      // Keep popup open - it will refresh when pick completes
    } else {
      setStatus(response && response.error ? response.error : "Could not start pick mode.");
    }
  });
}

for (const button of document.querySelectorAll(".repick-btn")) {
  button.addEventListener("click", async () => {
    const slot = button.getAttribute("data-slot");
    const cleared = await sendMessage({ type: "clearSlot", slot });
    if (!cleared || !cleared.ok) {
      setStatus(cleared && cleared.error ? cleared.error : `Could not clear ${slot} before repick.`);
      return;
    }
    const response = await sendMessage({ type: "beginPick", slot });
    if (response && response.ok) {
      setStatus(`Repick mode started for ${slot}. Click an element on the page.`);
      // Keep popup open - it will refresh when pick completes
    } else {
      setStatus(response && response.error ? response.error : "Could not start repick mode.");
    }
  });
}

for (const button of document.querySelectorAll(".clear-btn")) {
  button.addEventListener("click", async () => {
    const slot = button.getAttribute("data-slot");
    const response = await sendMessage({ type: "clearSlot", slot });
    if (response && response.ok) {
      setStatus(`${slot} cleared.`);
      renderState(response.state);
    } else {
      setStatus(response && response.error ? response.error : "Could not clear slot.");
    }
  });
}

document.getElementById("refresh-now").addEventListener("click", async () => {
  const response = await sendMessage({ type: "pollNow" });
  if (response && response.ok) {
    renderState(response.state);
    setStatus("Polled latest values.");
  } else {
    setStatus(response && response.error ? response.error : "Could not poll values.");
  }
});

for (const button of document.querySelectorAll(".test-btn")) {
  button.addEventListener("click", async () => {
    const slot = button.getAttribute("data-slot");
    const isActionSlot = ["buy-button", "sell-button", "close-button"].includes(slot);
    const response = await sendMessage({ type: isActionSlot ? "testActionSlot" : "pollSlot", slot });
    if (response && response.ok) {
      renderState(response.state);
      if (isActionSlot) {
        setStatus(`${slot} action fired${response.text ? `: ${response.text}` : "."}`);
      } else {
        const latest = response.state && response.state.latest ? response.state.latest[slot] : null;
        if (latest && latest.text) {
          setStatus(`${slot} test captured: ${latest.text}`);
        } else {
          setStatus(`${slot} test ran, but no element text was found.`);
        }
      }
    } else {
      setStatus(response && response.error ? response.error : `Could not test ${slot}.`);
    }
  });
}

document.getElementById("clear-all").addEventListener("click", async () => {
  const response = await sendMessage({ type: "clearAllSlots" });
  if (response && response.ok) {
    renderState(response.state);
    setStatus("All slots cleared.");
  } else {
    setStatus(response && response.error ? response.error : "Could not clear all slots.");
  }
});

document.getElementById("test-endpoint").addEventListener("click", async () => {
  const response = await sendMessage({ type: "testEndpoint" });
  if (response && response.ok) {
    renderState(response.state);
    setStatus("Endpoint test passed.");
  } else {
    if (response && response.state) {
      renderState(response.state);
    } else {
      const endpoint = response && response.endpoint ? response.endpoint : endpointInput.value.trim();
      setConnection(false, `App: unreachable (${endpoint || "unknown endpoint"})`);
    }
    setStatus(response && response.error ? response.error : "Endpoint test failed.");
  }
});

document.getElementById("toggle-live-trades").addEventListener("click", async () => {
  try {
    const response = await sendMessage({ type: "toggleLiveTrades" });
    if (response && response.ok) {
      setStatus("Live trades toggled.");
      // Delay to let app process, then refresh
      setTimeout(() => refresh(), 500);
    } else {
      const error = response && response.error ? response.error : "Could not toggle live trades.";
      setStatus(error);
      console.error("Toggle error:", error);
    }
  } catch (err) {
    const error = err?.message || "Toggle failed";
    setStatus(error);
    console.error("Toggle exception:", err);
  }
});

refresh();
setInterval(refresh, 1000);
