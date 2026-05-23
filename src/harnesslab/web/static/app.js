/* global fetch API */

let currentSessionId = null;
let busy = false;

const els = {
  sessionList: document.getElementById("session-list"),
  messages: document.getElementById("messages"),
  title: document.getElementById("chat-title"),
  status: document.getElementById("chat-status"),
  input: document.getElementById("input"),
  form: document.getElementById("composer"),
  sendBtn: document.getElementById("send-btn"),
  newChat: document.getElementById("new-chat"),
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

function setBusy(on) {
  busy = on;
  els.sendBtn.disabled = on;
  els.input.disabled = on;
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
  const data = await api(`/api/sessions/${id}`);
  els.title.textContent = data.session.title || data.session.goal;
  els.status.textContent = data.session.status;
  renderMessages(data.messages);
  await loadSessions();
}

function startNewChat() {
  currentSessionId = null;
  els.title.textContent = "新对话";
  els.status.textContent = "";
  renderMessages([]);
  els.input.focus();
  loadSessions();
}

async function sendMessage(text) {
  if (!text.trim() || busy) return;
  setBusy(true);
  try {
    let data;
    if (currentSessionId) {
      data = await api(`/api/sessions/${currentSessionId}/messages`, {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
    } else {
      data = await api("/api/sessions", {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
      currentSessionId = data.session.id;
    }
    els.title.textContent = data.session.title || data.session.goal;
    els.status.textContent = data.session.status;
    renderMessages(data.messages);
    await loadSessions();
  } catch (err) {
    showError(err.message);
  } finally {
    setBusy(false);
  }
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

loadSessions().catch((err) => showError(err.message));
