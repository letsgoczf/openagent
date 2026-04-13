from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from backend.config_loader import OpenAgentSettings
from backend.kernel.budget import Budget
from backend.kernel.trace import TraceWriter
from backend.models.base import ChatResponse, LLMAdapter
from backend.prompts.catalog import (
    AgentTemplateEntry,
    discover_agent_templates,
    format_catalog_for_planner,
)

_PLANNER_SYSTEM = """You are the top-level prompt orchestrator for OpenAgent.

You choose which agent prompt templates (by id) should shape downstream behavior. Templates are large Markdown system add-ons stored as prompts/<id>.agent.md.

Run mode:
- single: one agent answers (retrieval + tools). Use worker_templates only; synthesizer_templates MUST be an empty array [].
- multi: phase 1 is an analyst (retrieval + draft); phase 2 is a synthesizer that merges the draft. Pick worker_templates for the analyst and synthesizer_templates for the merger (may differ).

Rules:
- Only use template ids that appear in the catalog below. Never invent ids.
- Prefer 0–2 templates per side unless the user task clearly needs more.
- If unsure, return empty arrays for both.

Reply with ONLY valid JSON (no markdown fences, no other text):
{{"worker_templates":["id"],"synthesizer_templates":["id"],"rationale":"short"}}


Catalog:
{catalog}
"""


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    return t


def _parse_plan_json(text: str) -> dict[str, Any] | None:
    t = _strip_json_fence(text.strip())
    if not t:
        return None
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _coerce_id_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def _normalize_plan(
    data: dict[str, Any],
    *,
    allowed: set[str],
    mode: str,
    max_per_role: int,
) -> PromptPlan:
    worker = [i for i in _coerce_id_list(data.get("worker_templates")) if i in allowed]
    synth = [i for i in _coerce_id_list(data.get("synthesizer_templates")) if i in allowed]
    rationale = data.get("rationale")
    r = str(rationale).strip()[:500] if rationale is not None else ""

    if mode == "single":
        synth = []

    if max_per_role > 0:
        worker = worker[:max_per_role]
        synth = synth[:max_per_role]

    return PromptPlan(worker_templates=worker, synthesizer_templates=synth, rationale=r)


@dataclass(frozen=True)
class PromptPlan:
    worker_templates: list[str]
    synthesizer_templates: list[str]
    rationale: str


def _raw_preview(raw: Any, limit: int = 280) -> str:
    if isinstance(raw, ChatResponse):
        s = f"{raw.content or ''}\n{raw.thinking or ''}"
    else:
        s = str(raw)
    return s[:limit]


def plan_prompt_templates(
    *,
    query: str,
    mode: str,
    llm: LLMAdapter,
    budget: Budget,
    trace: TraceWriter | None,
    settings: OpenAgentSettings,
    catalog: list[AgentTemplateEntry] | None = None,
) -> PromptPlan:
    """
    调用一次生成模型，从目录中选择 worker / synthesizer 使用的模板 id。
    目录为空、预算不足或解析失败时返回空计划。
    """
    cfg = settings.prompt_management
    entries = catalog if catalog is not None else discover_agent_templates(settings=settings)
    allowed = {e.id for e in entries}

    if not cfg.enabled or not entries:
        if trace:
            trace.emit(
                "prompt_plan",
                {
                    "skipped": True,
                    "reason": "disabled_or_empty_catalog",
                    "catalog_size": len(entries),
                },
            )
        return PromptPlan([], [], "")

    if not budget.can_call_llm() or budget.wall_clock_exceeded():
        if trace:
            trace.emit(
                "prompt_plan",
                {"skipped": True, "reason": "budget"},
            )
        return PromptPlan([], [], "")

    mode_norm = "multi" if mode == "multi" else "single"
    catalog_text = format_catalog_for_planner(entries)
    system = _PLANNER_SYSTEM.format(catalog=catalog_text)
    user = (
        f"MODE: {mode_norm}\n\n"
        f"USER_TASK:\n{query.strip()[:4000]}\n"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        raw = llm.chat(messages, stream=False, max_tokens=cfg.planner_max_tokens)
    except Exception as e:  # noqa: BLE001
        if trace:
            trace.emit(
                "prompt_plan",
                {
                    "parse_ok": False,
                    "error": str(e),
                },
            )
        return PromptPlan([], [], "")

    data = _parse_plan_json(_raw_from_llm(raw))
    if data is None:
        if trace:
            trace.emit(
                "prompt_plan",
                {
                    "parse_ok": False,
                    "raw_preview": _raw_preview(raw),
                },
            )
        return PromptPlan([], [], "")

    plan = _normalize_plan(data, allowed=allowed, mode=mode_norm, max_per_role=cfg.max_templates_per_role)
    budget.record_llm_call()
    if trace:
        trace.emit(
            "prompt_plan",
            {
                "parse_ok": True,
                "mode": mode_norm,
                "worker_templates": plan.worker_templates,
                "synthesizer_templates": plan.synthesizer_templates,
                "rationale": plan.rationale,
            },
        )
    return plan


def _raw_from_llm(raw: Any) -> str:
    if isinstance(raw, ChatResponse):
        return (raw.content or "") + ("\n" + (raw.thinking or "") if raw.thinking else "")
    return str(raw)
