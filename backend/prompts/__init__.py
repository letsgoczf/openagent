"""Agent 提示词模板目录扫描与顶层规划（LLM 选择 worker / synthesizer 模板）。"""

from backend.prompts.catalog import (
    AgentTemplateEntry,
    discover_agent_templates,
    load_template_bodies,
)
from backend.prompts.mentions import extract_forced_agent_templates
from backend.prompts.planner import PromptPlan, plan_prompt_templates

__all__ = [
    "AgentTemplateEntry",
    "discover_agent_templates",
    "extract_forced_agent_templates",
    "load_template_bodies",
    "PromptPlan",
    "plan_prompt_templates",
]
