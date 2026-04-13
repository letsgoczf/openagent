from __future__ import annotations

from backend.registry.skill_registry import SkillManifest, SkillRegistry
from backend.registry.skill_tools import (
    merge_skill_tool_aliases,
    normalize_tool_names,
)


def test_normalize_tool_names_maps_case_insensitive() -> None:
    out = normalize_tool_names(
        ["Read", "WEB_SEARCH", "read"],
        {"read": "read_skill_reference", "web_search": "web_search"},
    )
    assert out == ["read_skill_reference", "web_search"]


def test_normalize_drops_empty_mapping_target() -> None:
    out = normalize_tool_names(["Bash", "web_search"], {"bash": ""})
    assert out == ["web_search"]


def test_normalize_preserves_unknown() -> None:
    out = normalize_tool_names(["custom_tool"], {})
    assert out == ["custom_tool"]


def test_merge_skill_tool_aliases_user_overrides_default() -> None:
    m = merge_skill_tool_aliases({"Read": "custom_reader"})
    assert m.get("Read") == "custom_reader"


def test_apply_tool_name_aliases_uses_builtin_read_mapping() -> None:
    reg = SkillRegistry()
    reg.register(
        SkillManifest(
            skill_id="x",
            name="",
            description="",
            tools_allowlist=["Read", "web_search"],
        )
    )
    reg.apply_tool_name_aliases(merge_skill_tool_aliases({}))
    assert reg.get("x").tools_allowlist == ["read_skill_reference", "web_search"]
