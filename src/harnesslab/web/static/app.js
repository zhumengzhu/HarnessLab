/* global fetch API */

let currentSessionId = null;
let busy = false;
let rememberMode = false;
let skillMode = false;

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
  skillBtn: document.getElementById("skill-btn"),
  rememberInline: document.getElementById("remember-inline"),
  skillInline: document.getElementById("skill-inline"),
  traceList: document.getElementById("trace-list"),
  clearTrace: document.getElementById("clear-trace"),
  settingsList: document.getElementById("settings-list"),
  proposalList: document.getElementById("proposal-list"),
  proposalDetail: document.getElementById("proposal-detail"),
  refreshProposals: document.getElementById("refresh-proposals"),
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

function visibleChatMessages(messages) {
  return messages.filter((m) => {
    if (m.role === "user") return true;
    if (m.role === "assistant") return Boolean((m.content || "").trim());
    // tool / system turns stay in session history for the model and trace panel.
    return false;
  });
}

function renderMessages(messages, toolCards = []) {
  els.messages.innerHTML = "";
  const visible = visibleChatMessages(messages);
  if (!visible.length && !toolCards.length) {
    els.messages.innerHTML = '<p class="empty-hint">发送第一条消息开始对话</p>';
    return;
  }
  for (const m of visible) {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    div.textContent = m.content;
    els.messages.appendChild(div);
  }
  for (const card of toolCards) {
    const div = document.createElement("div");
    div.className = `tool-card ${card.ok ? "ok" : "fail"}`;
    const title = document.createElement("div");
    title.className = "tool-card-title";
    title.textContent = `${card.tool || "tool"} · ${card.ok ? "ok" : "error"}`;
    const preview = document.createElement("pre");
    preview.className = "tool-card-preview";
    preview.textContent = card.error || card.output_preview || "";
    div.appendChild(title);
    div.appendChild(preview);
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
  els.skillBtn.disabled = !hasSession || busy;
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

async function loadSettings() {
  try {
    const data = await api("/api/settings");
    const s = data.settings || {};
    const rows = [
      ["模型", s.model_label || s.model_backend],
      ["DeepSeek", s.deepseek_model],
      ["Thinking", s.deepseek_thinking],
      ["Skill selection", s.skill_selection_mode],
      ["Planning mode", s.planning_mode],
      ["Budget enabled", s.budget?.enabled ? "yes" : "no"],
      ["Pre hooks", (s.hooks?.pre_tool || []).length],
      ["Post hooks", (s.hooks?.post_tool || []).length],
      ["Shell profile", s.shell_profile],
      ["Workspace", s.workspace],
      ["Config", s.config_path],
    ];
    els.settingsList.innerHTML = "";
    for (const [label, value] of rows) {
      if (!value) continue;
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      els.settingsList.appendChild(dt);
      els.settingsList.appendChild(dd);
    }
  } catch {
    els.settingsList.innerHTML = '<p class="empty-hint">无法加载设置</p>';
  }
}

async function loadProposals() {
  if (!els.proposalList) return;
  try {
    const data = await api("/api/proposals?status=open");
    const proposals = data.proposals || [];
    els.proposalList.innerHTML = "";
    if (!proposals.length) {
      els.proposalList.innerHTML = '<li class="empty-hint">暂无 open proposal</li>';
      if (els.proposalDetail) {
        els.proposalDetail.classList.add("hidden");
        els.proposalDetail.textContent = "";
      }
      return;
    }
    for (const p of proposals) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.innerHTML = `<strong>${escapeHtml(p.id)}</strong><span class="meta">${escapeHtml(p.kind || "")} · ${escapeHtml(String(p.occurrences || ""))}</span>`;
      btn.addEventListener("click", () => openProposal(p.id));
      li.appendChild(btn);
      els.proposalList.appendChild(li);
    }
  } catch {
    els.proposalList.innerHTML = '<li class="empty-hint">proposal 加载失败</li>';
  }
}

async function openProposal(id) {
  if (!els.proposalDetail) return;
  try {
    const data = await api(`/api/proposals/${id}`);
    const p = data.proposal || {};
    const lines = [
      `id: ${p.id || ""}`,
      `status: ${p.status || ""}`,
      `kind: ${p.kind || ""}`,
      `occurrences: ${p.occurrences || ""}`,
      `generated_at: ${p.generated_at || ""}`,
      "",
      p.body_markdown || "",
    ];
    els.proposalDetail.classList.remove("hidden");
    els.proposalDetail.textContent = lines.join("\n");
  } catch (err) {
    els.proposalDetail.classList.remove("hidden");
    els.proposalDetail.textContent = `加载失败: ${err.message || err}`;
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
  skillMode = false;
  els.rememberBtn.textContent = "记住";
  els.skillBtn.textContent = "技能";
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
  skillMode = false;
  els.rememberBtn.textContent = "记住";
  els.skillBtn.textContent = "技能";
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
  if (skillMode || trimmed.startsWith("/skill")) {
    skillMode = false;
    els.skillBtn.textContent = "技能";
    if (trimmed.startsWith("/skill")) return trimmed;
    return `/skill ${trimmed}`;
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
    renderMessages(data.messages, data.tool_cards || []);
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
  if (skillMode) {
    skillMode = false;
    els.skillBtn.textContent = "技能";
  }
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
  if (skillMode) {
    skillMode = false;
    els.skillBtn.textContent = "技能";
  }
  rememberMode = true;
  els.rememberBtn.textContent = "记住 ✓";
  const val = els.input.value;
  if (!val.startsWith("/remember ")) {
    els.input.value = `/remember ${val}`.trimEnd();
  }
  els.input.focus();
}

function toggleSkillMode() {
  if (rememberMode) {
    rememberMode = false;
    els.rememberBtn.textContent = "记住";
  }
  skillMode = !skillMode;
  els.skillBtn.textContent = skillMode ? "技能 ✓" : "技能";
  if (skillMode) {
    els.input.focus();
    if (!els.input.value.startsWith("/skill ")) {
      els.input.value = "/skill ";
      els.input.setSelectionRange(els.input.value.length, els.input.value.length);
    }
  }
}

function insertSkillPrefix() {
  if (rememberMode) {
    rememberMode = false;
    els.rememberBtn.textContent = "记住";
  }
  skillMode = true;
  els.skillBtn.textContent = "技能 ✓";
  const val = els.input.value;
  if (!val.startsWith("/skill ")) {
    els.input.value = `/skill ${val}`.trimEnd();
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
els.skillBtn.addEventListener("click", toggleSkillMode);
els.rememberInline.addEventListener("click", insertRememberPrefix);
els.skillInline.addEventListener("click", insertSkillPrefix);
els.clearTrace.addEventListener("click", clearTracePanel);
if (els.refreshProposals) {
  els.refreshProposals.addEventListener("click", () => {
    loadProposals().catch(() => {});
  });
}

clearTracePanel();
updateSessionActions();
loadSettings().catch(() => {});
loadSessions().catch((err) => showError(err.message));
loadProposals().catch(() => {});
