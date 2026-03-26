const DEFAULT_STATE = {
  endpoint: "http://127.0.0.1:8765/extension-feed",
  targets: {
    topstep: null,
    tradovate: null
  },
  latest: {
    topstep: null,
    tradovate: null
  },
  appConnection: {
    ok: null,
    lastSuccessAt: null,
    lastError: ""
  },
  liveTrades: false
};

async function getState() {
  const stored = await chrome.storage.local.get(["state"]);
  return {
    ...DEFAULT_STATE,
    ...(stored.state || {}),
    targets: {
      ...DEFAULT_STATE.targets,
      ...((stored.state || {}).targets || {})
    },
    latest: {
      ...DEFAULT_STATE.latest,
      ...((stored.state || {}).latest || {})
    },
    appConnection: {
      ...DEFAULT_STATE.appConnection,
      ...((stored.state || {}).appConnection || {})
    }
  };
}

async function setState(nextState) {
  await chrome.storage.local.set({ state: nextState });
}

async function updateState(mutator) {
  const state = await getState();
  const next = mutator(state) || state;
  await setState(next);
  return next;
}

async function ensureAlarm() {
  const alarm = await chrome.alarms.get("poll-targets");
  if (!alarm) {
    await chrome.alarms.create("poll-targets", { periodInMinutes: 1 / 60 });
  }
}

async function beginPick(slot) {
  const state = await getState();
  const existingTarget = state.targets && state.targets[slot];
  if (existingTarget && existingTarget.selector) {
    throw new Error(`${slot} is already selected. Clear it first to pick again.`);
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) {
    throw new Error("No active tab found.");
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      files: ["picker.js"]
    });

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: (pickSlot) => {
        if (typeof window.__elementDropperStartPick !== "function") {
          return false;
        }
        window.__elementDropperStartPick(pickSlot);
        return true;
      },
      args: [slot]
    });

    const started = (results || []).some((r) => r && r.result === true);
    if (!started) {
      throw new Error("Picker script did not start in this tab.");
    }
  } catch (err) {
    const msg = (err && err.message) ? err.message : String(err);
    if (msg.includes("Cannot access a chrome:// URL")) {
      throw new Error("Open a normal website tab first (not chrome:// pages).");
    }
    throw new Error(`Could not start picker on this tab: ${msg}`);
  }
}

async function testEndpoint(endpoint) {
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slot: "healthcheck",
        text: "ping",
        extracted: null,
        timestamp: new Date().toISOString()
      })
    });
    return response.ok;
  } catch (_err) {
    return false;
  }
}

function buildAppConnectionState(ok, errorText = "") {
  return {
    ok,
    lastSuccessAt: ok ? new Date().toISOString() : null,
    lastError: ok ? "" : String(errorText || "Could not reach app endpoint.")
  };
}

function safeNumber(text) {
  if (!text) {
    return null;
  }
  const match = text.match(/-?\d[\d.,]*/);
  return match ? match[0] : null;
}

async function postToApp(slot, text, state) {
  const payload = {
    slot,
    text: text || "",
    extracted: safeNumber(text),
    timestamp: new Date().toISOString()
  };

  try {
    const response = await fetch(state.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      return {
        ok: false,
        error: `App responded with ${response.status}`
      };
    }
    return { ok: true };
  } catch (_err) {
    return {
      ok: false,
      error: _err && _err.message ? _err.message : "App may be closed."
    };
  }
}

async function pollSlot(slot, state) {
  const target = state.targets[slot];
  if (!target || !target.selector || !target.tabId) {
    return state;
  }

  let text = null;
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: target.tabId },
      func: (selector) => {
        const el = document.querySelector(selector);
        return el ? (el.innerText || el.textContent || "").trim() : null;
      },
      args: [target.selector]
    });
    text = results && results[0] ? results[0].result : null;
  } catch (_err) {
    // Tab may be closed/navigation changed.
    text = null;
  }

  if (text === null) {
    return {
      ...state,
      latest: {
        ...state.latest,
        [slot]: state.latest[slot]
          ? {
              ...state.latest[slot],
              lastError: "Element not found on page."
            }
          : null
      }
    };
  }

  const latest = {
    ...state.latest,
    [slot]: {
      text,
      selector: target.selector,
      tabId: target.tabId,
      pageUrl: target.pageUrl,
      pageTitle: target.pageTitle,
      updatedAt: new Date().toISOString(),
      lastError: ""
    }
  };

  const postResult = await postToApp(slot, text, state);
  const nextState = {
    ...state,
    latest,
    appConnection: buildAppConnectionState(postResult.ok, postResult.error)
  };
  return nextState;
}

async function fetchLiveTradesStatus(state) {
  // Fetch live trades status from app
  try {
    const response = await fetch(state.endpoint.replace("/extension-feed", "/live-trades-status"), {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    });
    if (response.ok) {
      const data = await response.json();
      return !!data.enabled;
    }
  } catch (_err) {
    // If endpoint unavailable, try posting a query
  }
  return false;
}

async function pollAll() {
  let state = await getState();
  state = await pollSlot("topstep", state);
  state = await pollSlot("tradovate", state);
  state.liveTrades = await fetchLiveTradesStatus(state);
  await setState(state);
  return state;
}

async function pollOne(slot) {
  let state = await getState();
  state = await pollSlot(slot, state);
  state.liveTrades = await fetchLiveTradesStatus(state);
  await setState(state);
  return state;
}

chrome.runtime.onInstalled.addListener(async () => {
  await ensureAlarm();
  await setState(await getState());
});

chrome.runtime.onStartup.addListener(async () => {
  await ensureAlarm();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "poll-targets") {
    await pollAll();
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message.type === "getState") {
      sendResponse({ ok: true, state: await getState() });
      return;
    }

    if (message.type === "setEndpoint") {
      const endpoint = String(message.endpoint || "").trim();
      if (!endpoint) {
        sendResponse({ ok: false, error: "Endpoint is required." });
        return;
      }
      const state = await updateState((prev) => ({ ...prev, endpoint }));
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === "beginPick") {
      await beginPick(message.slot);
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "clearSlot") {
      const state = await updateState((prev) => ({
        ...prev,
        targets: { ...prev.targets, [message.slot]: null },
        latest: { ...prev.latest, [message.slot]: null }
      }));
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === "clearAllSlots") {
      const state = await updateState((prev) => ({
        ...prev,
        targets: { topstep: null, tradovate: null },
        latest: { topstep: null, tradovate: null }
      }));
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === "pollNow") {
      const state = await pollAll();
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === "pollSlot") {
      if (!["topstep", "tradovate"].includes(message.slot)) {
        sendResponse({ ok: false, error: "Unknown slot." });
        return;
      }
      const state = await pollOne(message.slot);
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === "testEndpoint") {
      const state = await getState();
      const reachable = await testEndpoint(state.endpoint);
      if (reachable) {
        const nextState = {
          ...state,
          appConnection: buildAppConnectionState(true)
        };
        await setState(nextState);
        sendResponse({ ok: true, reachable: true, endpoint: state.endpoint, state: nextState });
      } else {
        const nextState = {
          ...state,
          appConnection: buildAppConnectionState(false, `Could not reach app endpoint: ${state.endpoint}`)
        };
        await setState(nextState);
        sendResponse({
          ok: false,
          reachable: false,
          endpoint: state.endpoint,
          error: `Could not reach app endpoint: ${state.endpoint}`,
          state: nextState
        });
      }
      return;
    }

    if (message.type === "toggleLiveTrades") {
      const state = await getState();
      const payload = {
        slot: "toggle-live-trades",
        text: "",
        extracted: null,
        timestamp: new Date().toISOString()
      };

      try {
        const response = await fetch(state.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (response.ok) {
          sendResponse({ ok: true });
        } else {
          sendResponse({ ok: false, error: `App responded with ${response.status}` });
        }
      } catch (err) {
        sendResponse({ ok: false, error: err && err.message ? err.message : "Could not reach app." });
      }
      return;
    }

    if (message.type === "picked") {
      const currentState = await getState();
      const existingTarget = currentState.targets && currentState.targets[message.slot];
      if (existingTarget && existingTarget.selector) {
        sendResponse({
          ok: false,
          error: `${message.slot} is locked. Clear it first to pick another element.`
        });
        return;
      }

      const tabId = sender.tab ? sender.tab.id : null;
      const pageUrl = sender.tab ? sender.tab.url : "";
      const pageTitle = sender.tab ? sender.tab.title : "";
      const state = await updateState((prev) => ({
        ...prev,
        targets: {
          ...prev.targets,
          [message.slot]: {
            selector: message.selector,
            tabId,
            pageUrl,
            pageTitle,
            previewText: message.previewText || ""
          }
        }
      }));

      const updated = await pollSlot(message.slot, state);
      await setState(updated);
      sendResponse({ ok: true, state: updated });
      return;
    }

    sendResponse({ ok: false, error: "Unknown message type." });
  })().catch((err) => {
    sendResponse({ ok: false, error: err.message || String(err) });
  });

  return true;
});
