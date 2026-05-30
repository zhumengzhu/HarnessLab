# HarnessLab TS WebUI

本目录为 TypeScript 前端，架构说明见
[`docs/architecture/frontend-ts-migration.md`](../docs/architecture/frontend-ts-migration.md)，
UX 原则见 [`docs/architecture/webui-design.md`](../docs/architecture/webui-design.md)。

包管理以 **bun** 为准（`bun.lock` 为 lockfile）。

## 常用命令

```bash
cd webui
bun install
bun run dev
bun run build
bun run check
bun run test
bun run test:e2e
# 单文件 Vitest：
bun run vitest run src/features/proposals/ProposalPanel.test.tsx
```

构建产物输出到 `src/harnesslab/web/static_ts/`（gitignore；需先 `bun run build` 或 `./hl-serve build`）。
`./hl-serve build`（及 `restart --build`）会在 `build` 前执行 `bun run check`。

## 测试分层

Web 前端测试分三层，**不要与 Agent 浏览器（MCP Playwright）混淆**：

| 层级 | 命令 / 位置 | 浏览器 | 网络 |
| --- | --- | --- | --- |
| Vitest 单元/组件 | `bun run test` | 无（jsdom） | **mock `fetch`** |
| Vitest SSE 集成 | `src/lib/sse-client.test.ts` 等 | 无 | mock SSE 字节流 |
| Playwright E2E | `bun run test:e2e` | headless Chromium | **真实 localhost API** |
| Python pytest | 仓库根 `uv run pytest` | 无 | 测 API / loop，不测 DOM |

Vitest 在 `vite.config.ts` 中排除 `e2e/**`，避免与 Playwright 混跑。

架构说明：[`docs/architecture/frontend-ts-migration.md`](../docs/architecture/frontend-ts-migration.md) § Frontend testing coverage strategy。

## Playwright E2E

### 前置条件

1. `bun run build`（或仓库根 `./hl-serve build`），使 `harnesslab serve` 能托管 `static_ts/`。
2. CI 还会在 E2E 前安装 Python 依赖与 `bunx playwright install chromium`。

Playwright 通过 `playwright.config.ts` 的 `webServer` **自动启动** Python 服务：

```text
uv run harnesslab serve --model simple --host 127.0.0.1 --port 8787
```

就绪探测：`GET /api/health`。本地非 CI 时可复用已有 serve（`reuseExistingServer`）。

### 常用命令

| 目的 | 命令 |
| --- | --- |
| CI / 日常无头冒烟 | `bun run test:e2e` |
| 有界面浏览器 | `bun run test:e2e -- --headed` |
| 逐步调试 | `bun run test:e2e -- --debug` |
| 慢动作 | `bun run test:e2e -- --headed --slow-mo=800` |
| 交互式运行器 | `bun run test:e2e:ui` 或 `bunx playwright test --ui` |

默认 **headless**（无可见窗口），属正常现象。

### 当前覆盖范围

`e2e/smoke.spec.ts` 为 **UI 壳层冒烟**，使用真实 DOM 操作（`page.goto`、`getByRole`、`click`），**不是** mock 网络：

- 侧栏标题与 Chat 入口
- 对话 / Trace / Activity 标签
- Trace Spans / Events 切换
- Settings 与「界面偏好」

**尚未覆盖：** Composer 发消息、SSE 流式回复、slash 命令、完整 chat workflow。扩展 E2E 时仍应走真实 API（例如 `waitForResponse`），而非 `page.route` 拦截。

### 与 Agent 浏览器的区别

| | Web UI E2E | Agent MCP Playwright |
| --- | --- | --- |
| 目的 | 回归测试本仓库 Web UI | Agent 访问任意外部网站 |
| 配置 | `webui/playwright.config.ts` | `~/.config/harnesslab/config.json` MCP |
| 文档 | 本文 | [`docs/guides/browser-automation.md`](../docs/guides/browser-automation.md) |

## 简单聊天（3 步）

1. 构建 bundle（`./hl-serve build` 或 `bun run build`），在仓库根启动：`./hl-serve start` 或 `uv run harnesslab serve --workspace-root .`
2. 浏览器左侧 **Sessions** 面板点击 **新对话**
3. 底部 **Composer** 输入；输入 `/` 打开 slash 命令；Enter 发送（支持中文 IME）

**侧栏：** Chat · Proposals · Skills · Settings。Chat 下为会话列表。**界面偏好**（主题、Thought/Tool 密度、字号）在 **Settings**。

**主区域标签：** 对话 · Trace · Activity。Trace 默认 **Spans**（Jaeger 风格树）；**Events** 为原始 JSONL 调试视图。

刷新后最近会话与标签选择从 `localStorage` 恢复。

## 运行时切换

存在 `web/static_ts/`（`bun run build` 后）时，`harnesslab serve` **默认使用 TS bundle**（`HARNESSLAB_WEB_UI_VERSION` 默认为 `ts`）。

若 bundle 缺失，服务器返回 HTTP 503 及构建说明。

更多文档索引：[`docs/README.md`](../docs/README.md)。
