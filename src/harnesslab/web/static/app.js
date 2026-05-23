/* global fetch API */

let currentSessionId = null;
let busy = false;
let rememberMode = false;

const els = {
  sessionList: document.getElementById("session-list"),
  messages: document.getElementById("messages"),
  title: document.getElementById("chat-title"),
  status: document.getElementById("chat-status"),
  memoryNotes: document.getElementById("memory-notes"),
  input: document.getElementById("input"),
  form: document.getElementById("composer"),
  sendBtn: document.getElementById("send-btn"),
  newChat: document.getElementById("new-chat"),
  forkBtn: document.getElementById("fork-btn"),
  rememberBtn: document.getElementById("remember-btn"),
  rememberInline: document.getElementById("remember-inline"),
  traceList: document.getElementById("trace-list"),
  clearTrace: document.getElementById("clear-trace"),
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

function renderMessages(messages) {
  els.messages.innerHTML = "";
  if (!messages.length) {
    els.messages.innerHTML = '<p class="empty-hint">发送第一条消息开始对话</p>';
    return;
  }
  for (const m of messages) {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    div.textContent = m.content;
    els.messages.appendChild(div);
  }
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderMemoryNotes(notes) {
  if (!notes || !notes.trim()) {
    els.memoryNotes.classList.add("hidden");
    els.memoryNotes.textContent = "";
    return;
  }
  els.memoryNotes.classList.remove("hidden");
  els.memoryNotes.textContent = `Session memory:\n${notes}`;
}

function setBusy(on) {
  busy = on;
  els.sendBtn.disabled = on;
  els.input.disabled = on;
  els.forkBtn.disabled = on || !currentSessionId;
}

function updateSessionActions() {
  const hasSession = Boolean(currentSessionId);
  els.forkBtn.disabled = !hasSession || busy;
  els.rememberBtn.disabled = !hasSession || busy;
}

function clearTracePanel() {
  els.traceList.innerHTML = '<li class="empty-hint">暂无事件</li>';
}

function formatPayload(payload) {
  try {
    const text = JSON.stringify(payload);
    return text.length > 180 ? `${text.slice(0, 177)}…` : text;
  } catch {
    return String(payload);
  }
}

function appendTraceEvent(evt) {
  if (els.traceList.querySelector(".empty-hint")) {
    els.traceList.innerHTML = "";
  }
  const li = document.createElement("li");
  li.innerHTML = `<div class="evt-type">${escapeHtml(evt.event_type)}</div><div class="evt-payload">${escapeHtml(formatPayload(evt.payload))}</div>`;
  els.traceList.prepend(li);
}

function renderTraceEvents(events) {
  els.traceList.innerHTML = "";
  if (!events.length) {
    clearTracePanel();
    return;
  }
  for (const evt of events.slice().reverse()) {
    appendTraceEvent(evt);
  }
}

async function loadTraceForSession(id) {
  try {
    const data = await api(`/api/sessions/${id}/trace`);
    renderTraceEvents(data.events || []);
  } catch {
    clearTracePanel();
  }
}

async function loadSessions() {
  const data = await api("/api/sessions?limit=50");
  els.sessionList.innerHTML = "";
  for (const s of data.sessions) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = s.id === currentSessionId ? "active" : "";
    btn.innerHTML = `<strong>${escapeHtml(s.title || s.goal)}</strong><span class="meta">${s.status} · ${s.message_count} msgs</span>`;
    btn.addEventListener("click", () => openSession(s.id));
    li.appendChild(btn);
    els.sessionList.appendChild(li);
  }
}

async function openSession(id) {
  currentSessionId = id;
  rememberMode = false;
  els.rememberBtn.textContent = "记住";
  const data = await api(`/api/sessions/${id}`);
  els.title.textContent = data.session.title || data.session.goal;
  els.status.textContent = data.session.status;
  renderMessages(data.messages);
  renderMemoryNotes(data.session.memory_notes);
  await loadTraceForSession(id);
  updateSessionActions();
  await loadSessions();
}

function startNewChat() {
  currentSessionId = null;
  rememberMode = false;
  els.rememberBtn.textContent = "记住";
  els.title.textContent = "新对话";
  els.status.textContent = "";
  renderMessages([]);
  renderMemoryNotes(null);
  clearTracePanel();
  updateSessionActions();
  els.input.focus();
  loadSessions();
}

function prepareOutgoingText(text) {
  const trimmed = text.trim();
  if (!trimmed) return "";
  if (rememberMode || trimmed.startsWith("/remember ")) {
    rememberMode = false;
    els.rememberBtn.textContent = "记住";
    if (trimmed.startsWith("/remember ")) return trimmed;
    return `/remember ${trimmed}`;
  }
  return trimmed;
}

async function consumeSseResponse(res) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const block of parts) {
      const lines = block.split("\n");
      let eventType = "message";
      let dataLine = "";
      for (const line of lines) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        if (line.startsWith("data:")) dataLine = line.slice(5).trim();
      }
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine);
      if (eventType === "trace") appendTraceEvent(payload);
      if (eventType === "done") donePayload = payload;
      if (eventType === "error") throw new Error(payload.message || "stream error");
    }
  }
  if (!donePayload) throw new Error("stream ended without done event");
  return donePayload;
}

async function sendMessage(text) {
  const outgoing = prepareOutgoingText(text);
  if (!outgoing || busy) return;

  setBusy(true);
  const typing = document.createElement("div");
  typing.className = "typing-indicator";
  typing.textContent = "运行中…";
  els.messages.appendChild(typing);

  try {
    const url = currentSessionId
      ? `/api/sessions/${currentSessionId}/messages`
      : "/api/sessions";
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ message: outgoing, stream: true }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    const data = await consumeSseResponse(res);
    typing.remove();
    if (!currentSessionId) currentSessionId = data.session.id;
    els.title.textContent = data.session.title || data.session.goal;
    els.status.textContent = data.session.status;
    renderMessages(data.messages);
    renderMemoryNotes(data.session.memory_notes);
    await loadSessions();
  } catch (err) {
    typing.remove();
    showError(err.message);
  } finally {
    setBusy(false);
    updateSessionActions();
  }
}

async function forkSession() {
  if (!currentSessionId || busy) return;
  setBusy(true);
  try {
    const data = await api(`/api/sessions/${currentSessionId}/fork`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await openSession(data.session.id);
  } catch (err) {
    showError(err.message);
  } finally {
    setBusy(false);
  }
}

function toggleRememberMode() {
  rememberMode = !rememberMode;
  els.rememberBtn.textContent = rememberMode ? "记住 ✓" : "记住";
  if (rememberMode) {
    els.input.focus();
    if (!els.input.value.startsWith("/remember ")) {
      els.input.value = "/remember ";
      els.input.setSelectionRange(els.input.value.length, els.input.value.length);
    }
  }
}

function insertRememberPrefix() {
  rememberMode = true;
  els.rememberBtn.textContent = "记住 ✓";
  const val = els.input.value;
  if (!val.startsWith("/remember ")) {
    els.input.value = `/remember ${val}`.trimEnd();
  }
  els.input.focus();
}

function showError(msg) {
  const banner = document.createElement("div");
  banner.className = "error-banner";
  banner.textContent = msg;
  els.messages.prepend(banner);
  setTimeout(() => banner.remove(), 5000);
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = els.input.value;
  els.input.value = "";
  sendMessage(text);
});

els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    els.form.requestSubmit();
  }
});

els.newChat.addEventListener("click", startNewChat);
els.forkBtn.addEventListener("click", forkSession);
els.rememberBtn.addEventListener("click", toggleRememberMode);
els.rememberInline.addEventListener("click", insertRememberPrefix);
els.clearTrace.addEventListener("click", clearTracePanel);

clearTracePanel();
updateSessionActions();
loadSessions().catch((err) => showError(err.message));
