## OpenAgent Frontend Design Notes

> 前端代码位于 `openagent/frontend/src/`。
> **产品叙事**与 `OPENAGENT_ARCHITECTURE.md` 一致：界面与文案以 **智能体（Agent）** 为主干；「检索 / 证据」表现为 Agent 的可观测能力，避免把产品统称为「RAG 助手」。

## 本次交付：首页端到端实现

### 目标
- 实现 `"/"` 双语首页（中文简体 + 英文）并形成完整可访问交互路径。
- 视觉方向采用“大胆创新”：高对比深色基底 + 霓虹强调色 + 明确层级排版。
- 满足四项评估标准：Design quality、Originality、Craft、Functionality。

### 主要文件
- 入口与样式基座：
  - `src/app/layout.tsx`
  - `src/app/page.tsx`
  - `src/app/globals.css`
  - `src/styles/tokens.css`
  - `src/styles/motion.css`
- 首页组件：
  - `src/components/home/Hero.tsx`
  - `src/components/home/CapabilityGrid.tsx`
  - `src/components/home/WorkflowPreview.tsx`
  - `src/components/home/CTASection.tsx`
  - `src/components/home/LanguageToggle.tsx`
- 文案字典：
  - `src/lib/homeCopy.ts`
- 验证路由（保证主 CTA 可用）：
  - `src/app/workbench/page.tsx`
  - `src/app/docs/page.tsx`

### 设计与工程原则
- **Design quality**：全局设计令牌统一颜色、间距、圆角、阴影、动效节奏。
- **Originality**：避免默认模板结构，采用模块化异质卡片和品牌化首屏节奏。
- **Craft**：建立排版阶梯、响应式断点、focus-visible、按钮状态反馈。
- **Functionality**：主路径为「价值主张 -> 能力说明 -> 生产流程 -> CTA」。

### 交互与可访问性
- 语义化结构：`header` / `main` / `section` / `footer`。
- 键盘可达：提供 `Skip to content` 跳转与统一焦点高亮。
- 语言切换：`LanguageToggle` 使用 `aria-pressed` 告知当前激活语言。
- 链路完整：顶部导航和底部 CTA 可直接进入 `workbench` 与 `docs`。

### 测试与质量门禁
- 新增脚本：
  - `pnpm lint`
  - `pnpm typecheck`
  - `pnpm test`
- 新增测试：
  - `src/components/home/LanguageToggle.test.tsx`
  - `src/lib/homeCopy.test.ts`
  - `src/lib/wsPayload.test.ts`（WS payload 辅助函数）
  - `e2e/mock-subagents-ws.spec.ts`（`routeWebSocket` 模拟 ``chat.agent_*``，无需后端即可验子智能体侧栏）
- 通过标准：`lint + typecheck + test` 全部通过。

### 后续扩展建议
- 将首页双语状态提升为全站 i18n（可接入 `next-intl`）。
- 为 `workbench/docs` 逐步替换占位页面并接入真实 API。
- 增加 E2E 测试（Playwright）覆盖首页主任务链路。

- **Design quality:** Does the design feel like a coherent whole rather than a collection of parts? Strong work here means the colors, typography, layout, imagery, and other details combine to create a distinct mood and identity.
- **Originality:** Is there evidence of custom decisions, or is this template layouts, library defaults, and AI-generated patterns? A human designer should recognize deliberate creative choices. Unmodified stock components—or telltale signs of AI generation like purple gradients over white cards—fail here.
- **Craft:** Technical execution: typography hierarchy, spacing consistency, color harmony, contrast ratios. This is a competence check rather than a creativity check. Most reasonable implementations do fine here by default; failing means broken fundamentals.
- **Functionality:** Usability independent of aesthetics. Can users understand what the interface does, find primary actions, and complete tasks without guessing?