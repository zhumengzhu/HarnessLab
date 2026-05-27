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

## Token 流式（已落地）

- SSE：`reasoning_delta`、`assistant_delta`（DeepSeek 优先；需 thinking 模型）
- 后端：`stream_context` 绑定 loop → Web `_run_turn_sse`
- 前端：LiveTurn 增量渲染；delta 不参与 semantic replay compare

## 相关文档

- `docs/architecture/overview.md` — Web Chat 架构与端点
- `docs/architecture/data-model.md` — Message / TraceEvent 契约
- `docs/architecture/frontend-ts-migration.md` — TS WebUI 目录与 SSE 抽象
- `docs/architecture/model-parameters.md` — thinking / effort 控件
- [`docs/README.md`](../README.md) — full documentation index
