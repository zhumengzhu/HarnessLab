# WebUI Design

HarnessLab 的浏览器聊天界面（`harnesslab serve` / `./hl-serve`）遵循 **「Trace 是引擎，Chat 是产品」**
原则：运行时可观测性写入 span（`spans.jsonl`），用户-facing 体验由 Chat 区独立呈现。不打开 Trace
Tab **不得** 削弱核心对话能力（发送、停止、Thinking/Thought、Tool 活动、最终回复）。

## Design principles

1. **Never silent** — 发送后 200ms 内必须有可见反馈（乐观 User 气泡 + 活动指示）。
2. **Progressive disclosure** — Thinking / Tool / 长回复默认折叠；需要时再展开。
3. **Trace is engine, Chat is product** — Simple 模式不强迫用户阅读 JSON trace；trace 事件在
   前端翻译为聊天气泡内的结构化块（Thinking、Tool 行、Answer）。
4. **Provider-agnostic UI** — UI 只认 `thinking | tool | text` 三种块；vendor 差异留在 adapter。
5. **Two-tier streaming**
   - **Step 级（已落地）**：SSE `span.started` / `span.completed`（`harnesslab.step`、
     `llm.generate`、`tool.*`）驱动 Chat 活动，不依赖 LLM token streaming。
   - **Token 级（已落地，DeepSeek 优先）**：SSE `reasoning_delta` / `assistant_delta`；
     loop 经 ``stream_context`` 绑定 sink；Web UI LiveTurn 增量渲染。
6. **Replay stability** — span `metrics` 中 token 计数、latency、reasoning 正文为 **volatile**
   （不参与 semantic replay compare）；字段名与 API 契约在 `data-model.md` 维护。

## Turn layout (Chat)

一次 **Turn**（用户一发 → agent 直到 `final` / `ask_user`）在 Chat 区呈现为：

```
User message
└─ Assistant turn (in-flight or complete)
   ├─ [Thinking…] → [Thought for 3s ▾]   ← thinking 模型，每步 `llm.generate` 一条
   ├─ [Tool: web_search ▾]               ← 0..N，`tool.*` span 完成时实时追加
   └─ Final answer                        ← turn 结束 / `done` 后展示
```

Turn 完成后，Thinking / Tool 活动归档到该轮 terminal assistant 消息上（`turnEnrichments`），
刷新或切换会话后从 persisted spans + messages 重建（按 `turn_index` 对齐）。

## Thinking / Thought state machine

| 阶段 | UI 文案 | 触发 |
|------|---------|------|
| 推理中 | **Thinking…**（脉冲动画 + 计时） | SSE `span.started` `llm.generate` 且 `harnesslab.thinking.enabled` |
| 推理完成 | **Thought for {N}s ▾**（默认折叠） | `llm.generate` `span.completed` 含 `metrics.reasoning_text` 或 duration |
| 无 reasoning | 不显示 Thought 块 | 非 thinking 模型 / SimpleModel |

Thought 正文来源优先级：`message.reasoning_text`（API）> `llm.generate` span
`metrics.reasoning_text` > content 内 `<thinking>` 标签（legacy fallback）。

## Simple vs Advanced → unified shell (UI-6)

**Simple / Advanced 双模式已移除（2026-05）。** 单一产品壳：

| 区域 | 内容 |
|------|------|
| **Sidebar 顶栏** | Chat · Proposals · Skills · Settings |
| **Chat 导航下** | 会话搜索/列表、+新对话、Fork |
| **Settings** | **界面偏好**（主题、Thought/Tool 简洁/详细、字号）+ 运行时 config 快照 |
| **Session 主区 Tab** | 对话 · Trace · Activity |

Chat 区不再嵌入 Session metadata / Budget JSON / Tool messages 诊断块；预算与
原始事件见 **Trace**（Spans 或 Events）与 **Activity** Tab。

| 能力 | 位置 |
|------|------|
| User / Assistant / Turn 活动 | 对话 Tab |
| Thinking / Tool 折叠 | 对话 Tab（密度由 Settings 控制） |
| Context 圆环 | Composer |
| Trace span 树 + 事件调试 | Trace Tab（Spans 默认，Events 调试） |
| Activity 流 | Activity Tab |
| Proposals / Skills / 运行时 Settings | Sidebar 导航 |

## Trace 视图（UI-F2）

Trace Tab 顶层：**Timeline（Spans）** · **Events** · **JSONL**，同一 chrome 行内嵌
Checkpoints 折叠区（`SessionTraceView`）。

### Timeline（Spans，默认）

后端原生 `SpanRecord`（`parent_span_id` / `trace_id`），**Jaeger 借鉴布局**（非 1:1 复刻）：

| 区域 | 内容 |
| --- | --- |
| **主区（左）** | 全宽 waterfall：`Service & Operation \| Timeline` 两列合一；行内显示 `span.name`（如 `harnesslab.step`、`tool.fetch_url`）、可选 hint（model、policy denied）；IBM Carbon 风格 service 色；27px 紧凑行；可折叠子 span |
| **详情侧栏（右）** | 选中 span 的详情；默认打开；可收起（HarnessLab 扩展，Jaeger 侧栏通常常驻） |

**详情结构（Jaeger 式 accordion + KV 表）：**

- Header：operation 名、Service / Duration / Start Time
- **Tags** — `SpanRecord.attributes`（`harnesslab.live` 等内部键隐藏）
- **Process** — `SpanRecord.resource`（缺省时 fallback `service.name=harnesslab`）
- **Logs / Events** — 每条 event 嵌套 accordion + KV
- **Metrics** — `SpanRecord.metrics`（不含嵌套 `context`）
- **Prompt** — 仅 `llm.generate`：`ModelCallInspector`（`prompt_blocks` / `api_messages` / `context`）
- **Links** — 跨 trace 链接（如 sub-agent）

**其它：**

- 每 turn 一个 `trace_id`；多 turn session 提供 turn/trace 选择器
- **进行中 turn**：SSE `span.started` 占位 + 已完成 span 合并（`liveSpans.ts` / `mergeTraceSpans`）
- Raw JSONL 在 **JSONL** 子 Tab（`GET …/trace/jsonl`）

实现：`spanTree.ts`、`spanDisplay.ts`、`spanColor.ts`、`spanResource.ts`、
`liveSpans.ts`、`TraceSpanPanel.tsx`、`TraceSpanDetail.tsx`、
`TraceAttributesTable.tsx`、`TraceDetailAccordion.tsx`；
Live Turn / Activity 消费 span SSE（`liveTurnSpanReducer.ts`、`activityFeed.ts`）。

### Events（调试）

OpenClaw 式 **span 列表**（非 v1 `event_type` 流）：每条为一 completed
`SpanRecord` 摘要 + raw JSON；`llm.generate` 行内 Prompt inspector。

### JSONL

会话 `spans.jsonl` 行只读预览（与 persisted `span.completed` 一致）。

## Chat / Composer 减重方案（UI-7，待实施）

OpenClaw 对照下的 **下一视觉迭代**（本 PR 仅文档化，不改 Composer 结构）：

| 项 | 现状 | 目标 |
| --- | --- | --- |
| **Composer 首行** | Agent 模式 + 模型选择 + 工具栏并排 | **单行输入为主**；模型/模式收到 **⋯ 菜单** 或 Settings 默认 |
| **Context 圆环** | 与发送钮同排 | 保留；Compact 仅在高压时出现 |
| **队列/steer 提示** | 输入框上方 dashed 框 | **细条 badge**（「queued 2」点击展开） |
| **子 session 面板** | Chat 栈内卡片 | 折叠为 **侧栏会话树** 内 indent 或 Trace span |
| **消息气泡** | 多边框/嵌套 details | 减少外框；User 右对齐轻量气泡；Assistant 无 heavy panel |
| **Activity** | 独立 Tab | 保持；不在对话 Tab 堆叠 inline 条 |
| **Slash palette** | 绝对定位列表 | 保留；对齐 OpenClaw 命令面板宽度与键盘导航 |

**原则：** Chat Tab = 消息 + Composer；一切 operator 诊断进 Tab / Settings / Trace。

## OpenClaw 式 UI 迁移（UI-8）

借鉴 [OpenClaw Control UI](https://docs.openclaw.ai/web/control-ui) 的分组侧栏、顶栏、
Session 条、空态 Hero、Composer 卡片与设置抽屉；**不复刻** Channels / Cron / 语音等 gateway 能力。

**第一批（8a–8d + 8e 显隐/专注）已落地（2026-05）。** Trace / Activity Tab 视觉统一仍待后续小批次。

### UI-9：OpenClaw 式 Chat 审美（2026-05）

| 项 | 内容 |
| --- | --- |
| **气泡对话** | 用户右对齐粉调气泡；助手左对齐头像 + 名字/时间 + Context 按钮 |
| **Session 条** | 去掉顶栏「新对话」；模型单按钮 `Model · High`；移除 Trace 钟表 icon |
| **模型菜单** | 下拉改为向下展开，避免遮挡 |
| **i18n** | Settings 切换 中文 / English；侧栏、顶栏、Tab、Composer 等核心文案可本地化 |

### UI-10：OpenClaw 暖红 polish（2026-05）

| 项 | 内容 |
| --- | --- |
| **Light accent** | `#dc2626` 暖红（对齐 OpenClaw light） |
| **Dark accent** | `#ff5c5c` 签名红 |
| **Token 分层** | `--hl-bg-hover` / `--hl-accent-glow` / `--hl-focus-ring` / `color-mix` 边框 |
| **选中态** | 侧栏 nav、Session toggle、顶栏主题：inset 高光 + subtle shadow |
| **Settings** | 卡片网格 + `SegmentedControl`（neutral 档位，OpenClaw `qs-segmented` 风格） |
| **Context 用量色** | `ContextRing` / `MessageContextButton` / modal 百分比与环形色随 `--hl-accent` / warning / danger token，不再硬编码 GitHub 蓝 |
| **Context 交互（UI-11）** | 消息 footer `<details>` + Composer pill 点击展开 Cursor 式 breakdown；进度条按 **limit** 比例分段，轨道显示剩余 context |
| **New messages** | 用户上滑后若有新内容，滚动区下方居中显示「新消息」pill；对话区 thin scrollbar |
| **Skills 页（UI-11）** | OpenClaw 式卡片：hero 标题、scope tabs、filter + count、分组折叠列表、预览 dialog、本地安装区 |
| **Usage 页（UI-12）** | OpenClaw 式用量页预留：时间/指标控件（仅「全部」可用）、会话 `budget_usage` 汇总与表格；待 `/api/usage` |
| **Chat 顶栏** | 模型/控制栏不再随滚动折叠；仅 Composer 可 compact |

### 导航：保留 Session Tab（方案 B，已确认 2026-05）

Trace / Activity **继续放在主区 Tab**（对话 | Trace | Activity），**不**迁到侧栏「运行」组。

| 理由 | 说明 |
| --- | --- |
| 调整成本低 | Tab 与侧栏导航正交，后续改 IA 只动一层 |
| 会话上下文清晰 | 同一 session 下切换诊断视图，无需改侧栏选中态 |
| OpenClaw 差异可接受 | OpenClaw 用顶栏/侧栏进 Trace；我们用 Tab 等价 |

侧栏负责：**全局页**（Chat 入口 + 会话列表、Proposals、Skills、Settings）+ 分组/icon 视觉。
主区 Chat 视图：**Session Tab** +（UI-8）**ChatSessionHeader** + Hero + Composer。

后续若 Tab 显得冗余，可再评估「Trace 进侧栏、去掉 Tab」（方案 A），无需改后端。

### UI-8 分批（Tab 不变）

| 批次 | 内容 |
| --- | --- |
| **8a** | 设计 token；侧栏分组卡片 + icon |
| **8b** | 全局顶栏（面包屑、⌘K、主题三态） |
| **8c** | **ChatSessionHeader**（session chip、model、effort、🧠🔧↻）— 仅 **对话 Tab** |
| **8d** | Empty Hero + quick chips；Composer 卡片 + 齿轮设置抽屉 |
| **8e** | 思考/工具 **显隐** toggle、专注模式（与 Settings「简洁/详细」正交） |

Trace / Activity Tab 在 UI-8 中 **仅做视觉统一**（圆角、间距），不改信息架构。

## SSE 事件（Chat / Trace 消费）

Web UI 通过 `POST .../messages`（`stream: true`）订阅。Normative wire format：
[`web-api.md`](web-api.md) § Server-Sent Events。

| 事件 | 用途 |
| --- | --- |
| `span.started` | Live Turn / Activity / Trace Tab 进行中占位（未写入 JSONL） |
| `span.event` | Activity 即时事实（budget、policy deny、steer 等） |
| `span.completed` | 完整 `SpanRecord`；Trace Tab、JSONL 持久化 |
| `span.link` | 子 agent 跨 trace 链接 |
| `reasoning_delta` | Thinking 块逐字追加 |
| `assistant_delta` | 最终回答逐字追加 |
| `done` | 持久化 messages 对齐、清空 LiveTurn |
| `error` | 错误态 + 停止指示 |

v1 `event: trace` + `event_type` 扁平事件 **已退役**（Observability v2 cutover）。
Live Turn reducer 由 span 生命周期驱动（`liveTurnSpanReducer.ts`）。

## Trace：完整 Prompt 查看（Advanced）

`llm.generate` 完成 span 的 `metrics` 含：

- `prompt_blocks[]` — `{ name, role, origin, content, char_count }` 组装块全文
- `api_messages[]` — 序列化后发给 provider 的 chat messages（OpenAI 形状）
- `context` — 既有 `ContextSnapshot`（token 估算）
- `reasoning_text` — 可选，thinking 模型推理正文

Trace Tab 对 `llm.generate` span 展示 **Prompt inspector**（按 block 折叠 + API messages 全文），
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

## App shell（UI-1 + UI-6）

布局：`app-shell` **两列**（sidebar + main）。

| 区域 | 职责 |
|------|------|
| **Sidebar** (`AppSidebar`) | 顶栏 **Chat / Proposals / Skills / Settings**；Chat 下为会话搜索/列表 |
| **Main** (`app-main`) | Session Tab（对话/Trace/Activity）或 Proposals / Settings / Skills 页 |
| ~~Trace column~~ | **已移除** — Trace 在 Session **Trace Tab** 内 |

Chat 对话 Tab：`SessionWorkspace` 全高滚动 + 贴底 `ComposerPanel`（`app-composer-dock`）。

## Sidebar 会话搜索（UI-2）

侧栏「会话」区提供：

- **搜索框**：匹配标题、goal、session id、本地化状态文案（如「已完成」）
- **状态筛选**：全部 / 进行中 / 已完成 / 等待 / 子会话
- **计数**：筛选时显示 `匹配数 / 总数`；当前选中会话在筛选隐藏时仍置顶保留

实现：`filterSessions`（`webui/src/features/shell/filterSessions.ts`）。

## 活动展示与字号（UI-3 → UI-6）

**Settings → 界面偏好**（原侧栏 footer 控件已迁入）：

| 控件 | 行为 |
|------|------|
| **Thought / Tool · 简洁 / 详细** | 简洁：一行状态条；详细：可折叠块 |
| **主题 · 暗 / 亮** | `data-hl-theme` + `--hl-*` tokens |
| **A− / A+** | Chat 字号 `sm` / `md` / `lg` |

实现：`UiPreferencesPanel`、`ChatDisplayProvider`。

## Compact 按钮（UI-4a）

当 `ContextSnapshot` 显示上下文用量 **达到 compaction threshold**（或 ≥70% 窗口作为回退）时，Composer 工具栏在 Context 圆环旁显示 **Compact** 按钮。点击发送与斜杠命令等价的 `/compact`（走现有 `POST …/messages` SSE 路径）。

实现：`shouldSuggestCompaction`（`webui/src/features/chat/contextCompaction.ts`）、`ChatToolbar` 按钮、`useComposerController.sendCommand`。

## 侧栏重命名（UI-4a）

侧栏当前选中会话行提供 inline 重命名（铅笔 / 双击标题）。`PATCH /api/sessions/{id}` body `{ "title": "…" }`，标题最长 60 字符（与 `derive_title_from_text` 一致），持久化经 `SessionStorePort.save`。

## Activity 轻量面板（UI-4b + UI-6）

**Activity Tab**（非对话 Tab 内联）：

- 从 trace 子集推导；脱敏 tool args；会话内可清空
- 实现：`activityFeed.ts`、`ActivityPanel.tsx`

## Composer 滚动收起（UI-4b）

阅读历史消息 **向下滚动** 且离开底部时，Composer 进入 `composer-panel-compact`：隐藏 quick-actions、模型/模式选择器，保留输入框 + Context 圆环 + 发送/Compact。

回顶、回到底部、或 **向上滚动** 时恢复完整控件。实现：`useChatScroll` + `onComposerChromeChange`。

## 亮/暗主题（UI-4c → UI-6）

主题切换在 **Settings → 界面偏好**；`localStorage` key `harnesslab.uiTheme`。

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
| **Diagnostics** | Advanced mode toggles trace beside chat in one grid | Trace/logs in separate columns or nav pages | **Session Tab** Trace/Activity（UI-6+）；非第三列 |
| **Theming** | Ad-hoc GitHub-dark hex | Built-in themes + optional tweakcn import | CSS tokens (UI-1); optional themes later |
| **Tool/thinking UX** | Thought + tool cards (collapsible) | Simplified mode: status bars vs full EXEC | Phase UI-3 toggle |

### What we adopt vs skip

**Adopt (layout / IA, not pixel copy):**

- Sidebar navigation + session list
- Chat column fills viewport; composer fixed at bottom
- Trace/diagnostics in **Session Tab** (Trace / Activity), not competing with chat scroll
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
| **UI-1** | Design tokens; `app-shell` grid (sidebar + main); composer dock; full-height chat scroll | **Shipped** — `AppSidebar`, `app-chat-stack` |
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
| **UI-6** | 统一 shell；Settings 收拢偏好；Session Tab；移除 Simple/Advanced | **Shipped** |
| **UI-F2** | Trace Spans 树 + Events 调试双视图 | **Shipped** |
| **UI-7** | Chat/Composer OpenClaw 式减重 | **Shipped** — 见 UI-8 第一批 |
| **UI-8** | OpenClaw 式 shell；**保留 Session Tab（方案 B）** | **Shipped (batch 1: 8a–8e)** — Trace/Activity 视觉 polish 待定 |

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
