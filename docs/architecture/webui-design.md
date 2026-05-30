# WebUI Design

HarnessLab 的浏览器聊天界面（`harnesslab serve` / `./hl-serve`）遵循 **「Trace 是引擎，Chat 是产品」**
原则：运行时可观测性写入 trace，用户-facing 体验由 Chat 区独立呈现。禁用 Advanced 模式或 Trace
面板 **不得** 削弱核心对话能力（发送、停止、Thinking/Thought、Tool 活动、最终回复）。

## Design principles

1. **Never silent** — 发送后 200ms 内必须有可见反馈（乐观 User 气泡 + 活动指示）。
2. **Progressive disclosure** — Thinking / Tool / 长回复默认折叠；需要时再展开。
3. **Trace is engine, Chat is product** — Simple 模式不强迫用户阅读 JSON trace；trace 事件在
   前端翻译为聊天气泡内的结构化块（Thinking、Tool 行、Answer）。
4. **Provider-agnostic UI** — UI 只认 `thinking | tool | text` 三种块；vendor 差异留在 adapter。
5. **Two-tier streaming**
   - **Step 级（已落地）**：`step_started` / `model_call_started` / `model_call` / `tool_executed`
     驱动 Chat 活动，不依赖 LLM token streaming。
   - **Token 级（已落地，DeepSeek 优先）**：SSE `reasoning_delta` / `assistant_delta`；
     loop 经 ``stream_context`` 绑定 sink；Web UI LiveTurn 增量渲染。
6. **Replay stability** — trace 中 token 计数、latency、reasoning 正文为 **volatile**（不参与
   semantic replay compare）；字段名与 API 契约在 `data-model.md` 维护。

## Turn layout (Chat)

一次 **Turn**（用户一发 → agent 直到 `final` / `ask_user`）在 Chat 区呈现为：

```
User message
└─ Assistant turn (in-flight or complete)
   ├─ [Thinking…] → [Thought for 3s ▾]   ← thinking 模型，每步 model_call 一条
   ├─ [Tool: web_search ▾]               ← 0..N，trace tool_executed 实时追加
   └─ Final answer                        ← decision_made / done 后展示
```

Turn 完成后，Thinking / Tool 活动归档到该轮 terminal assistant 消息上（`turnEnrichments`），
刷新或切换会话后从 trace 重建（需 `user_input_received` 事件划分 turn 边界）。

## Thinking / Thought state machine

| 阶段 | UI 文案 | 触发 |
|------|---------|------|
| 推理中 | **Thinking…**（脉冲动画 + 计时） | `model_call_started` 或 `step_started` 且模型支持 reasoning |
| 推理完成 | **Thought for {N}s ▾**（默认折叠） | `model_call` 含 `reasoning_text` 或 `latency_ms` |
| 无 reasoning | 不显示 Thought 块 | 非 thinking 模型 / SimpleModel |

Thought 正文来源优先级：`message.reasoning_text`（API）> trace `model_call.reasoning_text` >
content 内 `<thinking>` 标签（legacy fallback）。

## Simple vs Advanced

| 能力 | Simple | Advanced |
|------|--------|----------|
| User / Assistant / Turn 活动 | ✅ | ✅ |
| Thinking / Tool 折叠 | ✅ | ✅ |
| Context 圆环 | ✅ | ✅ |
| Trace JSON 面板 | ❌ | ✅ |
| Session metadata / Budget | ❌ | ✅ |
| **完整 model prompt 查看** | ❌ | ✅（Trace 内 `model_call` → Prompt inspector） |

## SSE 事件（Chat 消费子集）

Web UI 通过 `POST .../messages`（`stream: true`）订阅：

| 事件 | Chat 用途 |
|------|-----------|
| `trace` | 增量更新 LiveTurn（step / thinking / tool） |
| `reasoning_delta` | Thinking 块逐字追加 reasoning |
| `assistant_delta` | 最终回答逐字追加 |
| `done` | 持久化 messages 对齐、清空 LiveTurn |
| `error` | 错误态 + 停止指示 |

`trace` 内常用 `event_type`：`step_started`、`model_call_started`、`model_call`、
`decision_made`、`tool_executed`、`tool_denied`。

## Trace：完整 Prompt 查看（Advanced）

每次 `model_call` trace payload 含：

- `prompt_blocks[]` — `{ name, role, origin, content, char_count }` 组装块全文
- `api_messages[]` — 序列化后发给 provider 的 chat messages（OpenAI 形状）
- `context` — 既有 `ContextSnapshot`（token 估算）
- `reasoning_text` — 可选，thinking 模型推理正文

Trace 面板对 `model_call` 展示 **Prompt inspector**（按 block 折叠 + API messages 全文），
供调试与上下文审计。Simple 模式用户不依赖此面板完成对话。

## Composer 交互（Cursor 风格）

- 左：Agent 模式 + 模型选择
- 输入 `/` 弹出命令/技能 palette（``GET /api/composer/commands``）
- 工作区技能：``/skillname <任务>`` 一次发送即 pin + 执行（Cursor 式）；仅 ``/skillname`` 则只 pin
- 内置：``/remember``、``/remember-global``、``/compact``；管理：``/skill list``
- 右：Context 圆环 + 发送 / 停止
- 运行中可继续输入；Enter 将消息 **入队** 顺序发送
- Stop 通过 `AbortController` 中断 SSE；保留已完成的 Thought / Tool 行
- **中文 IME**：composition 期间 Enter 不发送（`isComposing`）
- **会话恢复**：上次 session / Simple|Advanced 模式写入 `localStorage`
- **模型持久化**：模型选择器变更写入 `~/.config/harnesslab/config.json`

## 最终回复展示（Cursor 对齐）

User / Assistant **主对话**默认 **全文展示**，不提供 peek / 折叠三态（与 Cursor
主回复一致）。长回复靠会话滚动阅读。

- **Thinking / Tool** 仍用 `<details>` 左侧 disclosure 折叠（二级内容）
- **Advanced** 面板中的 raw `tool` 行可折叠，不影响 Simple 模式主对话

## App shell（UI-1）

布局：`app-shell` 三列网格（Simple 为两列）。

| 区域 | 职责 |
|------|------|
| **Sidebar** (`AppSidebar`) | 品牌、health、+新对话、Fork、**会话搜索/筛选**、会话列表、Simple/Advanced、Advanced 导航 |
| **Main** (`app-main`) | Chat 栈（消息 + 贴底 Composer）或 Proposals / Settings / Skills 页 |
| **Trace column**（Advanced + Chat） | `TracePanel` 独立列，不与 Chat 滚动竞争 |

Chat 区为 `app-chat-stack`：消息区 `flex: 1` 占满剩余高度，Composer 固定在底部（`app-composer-dock`）。

## Sidebar 会话搜索（UI-2）

侧栏「会话」区提供：

- **搜索框**：匹配标题、goal、session id、本地化状态文案（如「已完成」）
- **状态筛选**：全部 / 进行中 / 已完成 / 等待 / 子会话
- **计数**：筛选时显示 `匹配数 / 总数`；当前选中会话在筛选隐藏时仍置顶保留

实现：`filterSessions`（`webui/src/features/shell/filterSessions.ts`）。

## 活动展示与字号（UI-3）

侧栏底部 **阅读偏好**：

| 控件 | 行为 |
|------|------|
| **活动 · 简洁 / 详细** | 简洁：Thought / Tool 仅一行状态条，正文点击展开；详细：保持 UI-1 前默认可折叠块 |
| **A− / A+** | 调整 Chat 正文与 Composer 字号（`sm` / `md` / `lg`，写入 `localStorage`） |

实现：`ChatDisplayProvider`、`ToolCardRow`、`ThinkingBlock` 的 `displayMode` prop。

## Compact 按钮（UI-4a）

当 `ContextSnapshot` 显示上下文用量 **达到 compaction threshold**（或 ≥70% 窗口作为回退）时，Composer 工具栏在 Context 圆环旁显示 **Compact** 按钮。点击发送与斜杠命令等价的 `/compact`（走现有 `POST …/messages` SSE 路径）。

实现：`shouldSuggestCompaction`（`webui/src/features/chat/contextCompaction.ts`）、`ChatToolbar` 按钮、`useComposerController.sendCommand`。

## 侧栏重命名（UI-4a）

侧栏当前选中会话行提供 inline 重命名（铅笔 / 双击标题）。`PATCH /api/sessions/{id}` body `{ "title": "…" }`，标题最长 60 字符（与 `derive_title_from_text` 一致），持久化经 `SessionStorePort.save`。

## Activity 轻量面板（UI-4b）

Chat 与 Composer 之间的 **Activity** 条（Simple + Advanced 均可见）：

- 从 trace 子集推导：`step_started`、`model_call_started`、`tool_executed`、`tool_denied`、compaction 事件
- **脱敏**：不展示 tool args 值，仅显示字段数量；output 为截断 preview
- 浏览器会话内有效；**清空**后仅跟踪新一轮 SSE trace；切换会话重置
- 实现：`activityFeed.ts`、`ActivityPanel.tsx`

## Composer 滚动收起（UI-4b）

阅读历史消息 **向下滚动** 且离开底部时，Composer 进入 `composer-panel-compact`：隐藏 quick-actions、模型/模式选择器，保留输入框 + Context 圆环 + 发送/Compact。

回顶、回到底部、或 **向上滚动** 时恢复完整控件。实现：`useChatScroll` + `onComposerChromeChange`。

## 亮/暗主题（UI-4c）

侧栏 **主题 · 暗 / 亮** 切换，写入 `localStorage`（`harnesslab.uiTheme`）。`document.documentElement` 设置 `data-hl-theme`；CSS `--hl-*` tokens 在 dark/light 间切换；代码块高亮同步换用 highlight.js `github-dark` / `github` 主题。

Composer 输入框字号 `max(16px, var(--hl-chat-font-size))`，避免移动端 Safari 聚焦放大。

## 后续（UI-5，需 backend）

| 项 | 说明 |
| --- | --- |
| **Steer** | 运行中将队列消息注入当前 turn（OpenClaw 式） | **Done (UI-5b)** |
| **Per-session model** | 会话级 model/thinking 覆盖，非全局 `config.json` | **Done (UI-5a)** |

## Chat scroll（Simple + Advanced）

长会话在 **Chat 消息区** 内滚动（全高 flex + `overflow-y`）：

- 默认 **stick-to-bottom**：新消息与流式 delta 自动滚到底。
- 用户上滚后暂停跟随，右下角 **「↓ 最新」** 恢复并滚到底。
- 实现：`ChatScrollArea` + `useChatScroll`（`webui/src/features/chat/`）。

本地改 Web UI 后执行 **`./hl-serve restart --build`**（rebuild TS bundle + restart serve）。

## Token 流式（已落地）

- SSE：`reasoning_delta`、`assistant_delta`（DeepSeek 优先；需 thinking 模型）
- 后端：`stream_context` 绑定 loop → Web `_run_turn_sse`
- 前端：LiveTurn 增量渲染；delta 不参与 semantic replay compare

## Visual reference: OpenClaw Control UI

HarnessLab is **not** an OpenClaw gateway replacement (`docs/why-harnesslab.md`).
The TS WebUI may still borrow **layout and information architecture** from
[OpenClaw Control UI](https://docs.openclaw.ai/web/control-ui) where it improves
the chat-first product without copying unused gateway surfaces (Channels, Cron,
Nodes, …).

### Comparison (2026-05)

| Dimension | HarnessLab (pre–UI-1) | OpenClaw Control UI | HarnessLab target |
| --- | --- | --- | --- |
| **Structure** | Document page: header → session dropdown → stacked panels | App shell: **sidebar + main + optional trace** | App shell (UI-1+) |
| **Chat** | Message panel with capped height scroll | Full-height chat; **composer pinned bottom** | Full-height + docked composer |
| **Sessions** | Top dropdown picker | Sidebar session list | Sidebar list (UI-1) |
| **Diagnostics** | Advanced mode toggles trace beside chat in one grid | Trace/logs in separate columns or nav pages | Trace column in Advanced (UI-1) |
| **Theming** | Ad-hoc GitHub-dark hex | Built-in themes + optional tweakcn import | CSS tokens (UI-1); optional themes later |
| **Tool/thinking UX** | Thought + tool cards (collapsible) | Simplified mode: status bars vs full EXEC | Phase UI-3 toggle |

### What we adopt vs skip

**Adopt (layout / IA, not pixel copy):**

- Sidebar navigation + session list
- Chat column fills viewport; composer fixed at bottom
- Trace/diagnostics in a side column (Advanced), not competing with chat scroll
- Central design tokens (`--hl-*` in `webui/src/styles.css`)

**Skip (feature shell without backend):**

- Channels / Cron / Nodes / Dreams nav tabs
- WebSocket RPC dashboard pages (HarnessLab stays REST + SSE)
- Full OpenClaw theme marketplace in v1

Reference only — do **not** copy OpenClaw CSS/assets verbatim; reimplement tokens
and components under `webui/`.

### Visual evolution phases

| Phase | Scope | Status |
| --- | --- | --- |
| **UI-1** | Design tokens; `app-shell` grid (sidebar + main + trace column); composer dock; full-height chat scroll | **Shipped** — `AppSidebar`, `app-chat-stack` |
| **UI-2** | Sidebar polish; remove legacy session dropdown; session search/filter | **Shipped** — `filterSessions`, sidebar search + status chips |
| **UI-3** | Tool/thought simplified output toggle; optional text size control | **Shipped** — 简洁/详细活动、A−/A+ 字号 |
| **UI-4a** | Context 高压 **Compact** 按钮；侧栏 **会话重命名** | **Shipped** |
| **UI-4b** | Activity 轻量面板；滚动收起 Composer 控件 | **Shipped** |
| **UI-4c** | 亮/暗主题切换 | **Shipped** — `data-hl-theme`, sidebar 主题 toggle |
| **UI-5** | Steer 排队注入当前 turn；会话级 model/thinking 覆盖 | **Done** |

### UI-4 backlog (approved 2026-05)

Prioritized borrowings after UI-1–3 (see discussion; not OpenClaw gateway shell):

| Priority | Item | Rationale |
| --- | --- | --- |
| **4a** | Compact button near Context ring | Surfaces existing `/compact`; threshold already in `ContextSnapshot` |
| **4a** | Sidebar session rename | Auto-title exists; operators need manual labels |
| **4b** | Browser-local Activity stream | Lighter than Trace JSON for Simple users |
| **4b** | Collapse composer chrome on scroll down | Long transcripts stay immersive |
| **4c** | Light/dark theme toggle | **Shipped** |
| **UI-5** | Steer queued message; per-session model override | **Done** |

**Skip:** Channels, Cron, Nodes, Talk/voice, PWA push, WebSocket RPC dashboard, device pairing.

Local rebuild after Web UI edits:

```bash
./hl-serve restart --build
```

## 相关文档

- `docs/architecture/overview.md` — Web Chat 架构与端点
- `docs/architecture/data-model.md` — Message / TraceEvent 契约
- `docs/architecture/frontend-ts-migration.md` — TS WebUI 目录与 SSE 抽象
- `docs/architecture/model-parameters.md` — thinking / effort 控件
- [`docs/README.md`](../README.md) — full documentation index
