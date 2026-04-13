from __future__ import annotations

from pathlib import Path

from backend.registry.skill_md import parse_skill_md
from backend.registry.skill_registry import SkillRegistry


def test_parse_skill_md_minimal(tmp_path: Path) -> None:
    d = tmp_path / "demo-skill"
    d.mkdir()
    f = d / "SKILL.md"
    f.write_text(
        """---
name: demo-skill
description: Demo for tests. Use when unit testing skill loading.
allowed-tools: web_search tool_a
metadata:
  trigger_keywords: "foo,bar"
  display_name: "Demo"
---

## Body

Hello **world**.
""",
        encoding="utf-8",
    )
    w: list[str] = []
    m = parse_skill_md(f, expected_dir_name="demo-skill", warnings=w)
    assert m is not None
    assert m.skill_id == "demo-skill"
    assert m.name == "Demo"
    assert "Hello **world**" in m.prompt_addon
    assert m.tools_allowlist == ["web_search", "tool_a"]
    assert "foo" in m.trigger_keywords and "bar" in m.trigger_keywords
    assert w == []


def test_parse_skill_md_dir_name_mismatch(tmp_path: Path) -> None:
    d = tmp_path / "right-name"
    d.mkdir()
    f = d / "SKILL.md"
    f.write_text(
        "---\nname: wrong-name\ndescription: x\n---\n\nbody\n",
        encoding="utf-8",
    )
    w: list[str] = []
    m = parse_skill_md(f, expected_dir_name="right-name", warnings=w)
    assert m is None
    assert any("skipped" in x for x in w)


def test_parse_skill_md_openagent_enabled_false(tmp_path: Path) -> None:
    d = tmp_path / "off-skill"
    d.mkdir()
    f = d / "SKILL.md"
    f.write_text(
        """---
name: off-skill
description: off
metadata:
  openagent_enabled: false
---

nope
""",
        encoding="utf-8",
    )
    w: list[str] = []
    m = parse_skill_md(f, expected_dir_name="off-skill", warnings=w)
    assert m is None


def test_read_skill_md_body(tmp_path: Path) -> None:
    from backend.registry.skill_md import read_skill_md_body

    f = tmp_path / "SKILL.md"
    f.write_text("---\na: 1\n---\n\n**hi**\n", encoding="utf-8")
    assert read_skill_md_body(f) == "**hi**"


def test_defer_body_loads_on_prompt_resolve(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"
    pkg = skill_root / "lazy-skill"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(
        """---
name: lazy-skill
description: test
metadata:
  trigger_keywords: "lazytrigger"
---

LAZY_BODY
""",
        encoding="utf-8",
    )
    reg = SkillRegistry()
    reg.load_from_skills_directory(skill_root, defer_body=True)
    m = reg.get("lazy-skill")
    assert m is not None
    assert m.prompt_addon == ""
    assert m.skill_md_path is not None
    addons = reg.get_prompt_addons("use lazytrigger please")
    assert addons == ["LAZY_BODY"]


def test_load_from_skills_directory_skips_underscore_dir(tmp_path: Path) -> None:
    (tmp_path / "_hidden").mkdir()
    (tmp_path / "_hidden" / "SKILL.md").write_text(
        "---\nname: bad\n---\n", encoding="utf-8"
    )
    reg = SkillRegistry()
    reg.load_from_skills_directory(tmp_path)
    assert reg.get("bad") is None


def test_yaml_overrides_disk_skill(tmp_path: Path) -> None:
    from backend.config_loader import (
        EmbeddingConfig,
        GenerationConfig,
        ModelsConfig,
        OpenAgentSettings,
        SkillItemConfig,
        SkillsBundleConfig,
        StorageConfig,
        TokenizationConfig,
    )
    from backend.registry.service import build_registry_service

    skill_root = tmp_path / "skills"
    pkg = skill_root / "override-me"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(
        """---
name: override-me
description: from disk
allowed-tools: web_search
metadata:
  trigger_keywords: "hit"
---

DISK_BODY
""",
        encoding="utf-8",
    )

    settings = OpenAgentSettings(
        models=ModelsConfig(
            generation=GenerationConfig(
                provider="ollama",
                model_id="m",
                base_url="http://127.0.0.1:11434",
            ),
            embedding=EmbeddingConfig(
                provider="ollama",
                model_id="e",
                base_url="http://127.0.0.1:11434",
                vector_dimensions=4,
            ),
        ),
        storage=StorageConfig(sqlite_path=str(tmp_path / "db.sqlite")),
        tokenization=TokenizationConfig(provider="auto"),
        skills_bundle=SkillsBundleConfig(enabled=True, skills_dir=str(skill_root)),
        skills=[
            SkillItemConfig(
                skill_id="override-me",
                name="YAML layer",
                description="yaml desc",
                trigger_keywords=["hit"],
                tools_allowlist=["web_search"],
                prompt_addon="YAML_BODY",
                enabled=True,
            )
        ],
    )
    svc = build_registry_service(settings)
    m = svc.skill_registry.get("override-me")
    assert m is not None
    assert m.prompt_addon == "YAML_BODY"
    assert "DISK_BODY" not in m.prompt_addon
