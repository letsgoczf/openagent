---
name: web-research
description: Search the public web for fresh facts, news, or external references. Use when the user asks to look something up online, search the internet, or needs current events (中文：搜索网络、查资料、最新资讯).
allowed-tools: WebSearch Read
metadata:
  display_name: "Web research"
  trigger_keywords: "search,google,搜索,互联网,网上,查一下,lookup,web"
  tags: "search,agentskills"
---

## When activated

- Prefer **web_search** (SKILL 里可写 ``WebSearch``，会自动映射) when fresh external facts are needed.
- Use **read_skill_reference**（SKILL 里可写 ``Read``）与 `skill_id: web-research`、`references/…` 读取 L3 说明。
- Summarize results in your own words; do not fabricate URLs or quotes.
- If the user only needs internal document evidence, rely on the EVIDENCE block instead.

## Style

- Keep answers concise; cite that information came from web search when appropriate.
