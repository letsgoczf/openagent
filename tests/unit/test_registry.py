"""P6 Registry 单元测试：未注册 tool 拒绝、白名单控制、RAG collection 受限、Skill 匹配与工具集。"""

from __future__ import annotations

import pytest

from backend.registry.rag_registry import RagCollection, RagRegistry
from backend.registry.service import build_registry_service
from backend.registry.skill_registry import SkillManifest, SkillRegistry
from backend.registry.tool_gateway import ToolCallResult, ToolGateway
from backend.registry.tool_registry import ToolDefinition, ToolRegistry


# ──────────────────────────────────────────────────────────────────────────────
# ToolRegistry
# ──────────────────────────────────────────────────────────────────────────────

class TestToolRegistryBasic:
    """注册与查询。"""

    def setup_method(self) -> None:
        self.reg = ToolRegistry()
        self.reg.register(ToolDefinition(name="search", description="search docs", input_schema={}))
        self.reg.register(
            ToolDefinition(
                name="compute",
                description="compute math",
                input_schema={
                    "type": "object",
                    "properties": {"expr": {"type": "string"}},
                    "required": ["expr"],
                },
                enabled=False,
            )
        )

    def test_get_existing(self) -> None:
        tool = self.reg.get("search")
        assert tool is not None
        assert tool.name == "search"

    def test_get_non_existing(self) -> None:
        assert self.reg.get("nonexistent") is None

    def test_list_enabled(self) -> None:
        tools = self.reg.list_enabled()
        assert len(tools) == 1
        assert tools[0].name == "search"

    def test_load_from_config(self) -> None:
        reg2 = ToolRegistry()
        reg2.load_from_config([
            {"name": "a", "description": "A", "input_schema": {}},
            {"name": "b", "description": "B", "input_schema": {}, "enabled": True},
        ])
        assert reg2.get("a") is not None
        assert reg2.get("b") is not None

    def test_schemas_output(self) -> None:
        schemas = self.reg.get_all_schemas()
        assert len(schemas) == 1  # 只有 enabled 的
        assert schemas[0]["function"]["name"] == "search"


class TestToolRegistryAllowlist:
    """权限控制：白名单 / 禁用 / 不存在。"""

    def setup_method(self) -> None:
        self.reg = ToolRegistry()
        self.reg.register(ToolDefinition(name="search", description="", input_schema={}))
        self.reg.register(ToolDefinition(name="read", description="", input_schema={}))
        self.reg.register(
            ToolDefinition(name="disabled", description="", input_schema={}, enabled=False)
        )

    def test_allowed_no_restrictions(self) -> None:
        ok, reason = self.reg.is_tool_allowed("search")
        assert ok is True
        assert reason == ""

    def test_allowlist_pass(self) -> None:
        self.reg.set_allowlist(["search", "read"])
        ok, reason = self.reg.is_tool_allowed("search")
        assert ok is True

    def test_allowlist_reject(self) -> None:
        self.reg.set_allowlist(["search"])
        ok, reason = self.reg.is_tool_allowed("read")
        assert ok is False
        assert reason == "tool_not_in_allowlist"

    def test_disabled_tool(self) -> None:
        ok, reason = self.reg.is_tool_allowed("disabled")
        assert ok is False
        assert reason == "tool_disabled"

    def test_unknown_tool(self) -> None:
        ok, reason = self.reg.is_tool_allowed("unknown")
        assert ok is False
        assert reason == "tool_not_found"

    def test_allowlist_none_disables(self) -> None:
        self.reg.set_allowlist(["search"])
        self.reg.set_allowlist(None)
        ok, reason = self.reg.is_tool_allowed("read")
        assert ok is True


class TestToolRegistryValidation:
    """JSON Schema 校验（轻量）。"""

    def test_valid_arguments(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolDefinition(
                name="calc",
                description="",
                input_schema={
                    "type": "object",
                    "properties": {"expr": {"type": "string"}},
                    "required": ["expr"],
                },
            )
        )
        ok, msg = reg.validate_arguments("calc", {"expr": "1+1"})
        assert ok is True

    def test_missing_required(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolDefinition(
                name="calc",
                description="",
                input_schema={
                    "type": "object",
                    "properties": {"expr": {"type": "string"}},
                    "required": ["expr"],
                },
            )
        )
        ok, msg = reg.validate_arguments("calc", {})
        assert ok is False
        assert "missing" in msg

    def test_type_mismatch(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolDefinition(
                name="calc",
                description="",
                input_schema={
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                },
            )
        )
        ok, msg = reg.validate_arguments("calc", {"count": "not_an_int"})
        assert ok is False


# ──────────────────────────────────────────────────────────────────────────────
# ToolGateway
# ──────────────────────────────────────────────────────────────────────────────

class TestToolGateway:
    """网关执行：权限 → 校验 → 执行 → 结果。"""

    def setup_method(self) -> None:
        self.reg = ToolRegistry()
        self.reg.register(ToolDefinition(name="echo", description="", input_schema={}))
        self.reg.register(ToolDefinition(name="bad", description="", input_schema={}, enabled=False))
        self.gw = ToolGateway(self.reg)

    def test_successful_handler(self) -> None:
        self.gw.register_handler("echo", lambda x="hello": f"echo:{x}")
        result = self.gw.execute("echo", {"x": "world"})
        assert result.success is True
        assert result.output == "echo:world"
        assert result.preview == "echo:world"
        assert result.elapsed_ms >= 0

    def test_tool_not_found(self) -> None:
        result = self.gw.execute("nonexistent", {})
        assert result.success is False
        assert result.error_code == "tool_not_found"

    def test_disabled_tool(self) -> None:
        result = self.gw.execute("bad", {})
        assert result.success is False
        assert result.error_code == "tool_disabled"

    def test_handler_error(self) -> None:
        self.gw.register_handler("echo", lambda: 1 / 0)
        result = self.gw.execute("echo", {})
        assert result.success is False
        assert result.error_code == "handler_error"

    def test_preview_truncation(self) -> None:
        self.gw.register_handler("echo", lambda: "A" * 1000)
        result = self.gw.execute("echo", {})
        assert result.success is True
        assert len(result.preview) <= 503  # 500 + "..."

    def test_secret_masking(self) -> None:
        masked = ToolGateway._mask_secrets("key=abcdef1234567890 and token=mysecrettoken")
        assert "key=***" in masked
        assert "token=***" in masked


# ──────────────────────────────────────────────────────────────────────────────
# RagRegistry
# ──────────────────────────────────────────────────────────────────────────────

class TestRagRegistryBasic:
    """RAG 集合注册与查询。"""

    def setup_method(self) -> None:
        self.reg = RagRegistry()
        self.reg.register(RagCollection(collection_id="docs", description="Docs"))
        self.reg.register(
            RagCollection(collection_id="disabled", description="Disabled", enabled=False)
        )

    def test_get_existing(self) -> None:
        c = self.reg.get("docs")
        assert c is not None
        assert c.collection_id == "docs"

    def test_get_non_existing(self) -> None:
        assert self.reg.get("unknown") is None

    def test_list_enabled(self) -> None:
        assert len(self.reg.list_enabled()) == 1

    def test_is_allowed_true(self) -> None:
        assert self.reg.is_collection_allowed("docs") is True

    def test_is_allowed_disabled(self) -> None:
        assert self.reg.is_collection_allowed("disabled") is False

    def test_is_allowed_non_existing(self) -> None:
        assert self.reg.is_collection_allowed("unknown") is False

    def test_collection_ids(self) -> None:
        assert set(self.reg.collection_ids()) == {"docs", "disabled"}

    def test_get_allowed_ids(self) -> None:
        assert self.reg.get_allowed_ids() == ["docs"]


# ──────────────────────────────────────────────────────────────────────────────
# SkillRegistry
# ──────────────────────────────────────────────────────────────────────────────

class TestSkillRegistryBasic:
    """Skill 注册与匹配。"""

    def setup_method(self) -> None:
        self.reg = SkillRegistry()
        self.reg.register(
            SkillManifest(
                skill_id="code",
                name="代码助手",
                description="",
                trigger_keywords=["代码", "分析"],
                tools_allowlist=["read_file", "search_codebase"],
                prompt_addon="分析代码。",
            )
        )
        self.reg.register(
            SkillManifest(
                skill_id="general",
                name="通用助手",
                description="",
                trigger_keywords=[],
                tools_allowlist=[],
            )
        )
        self.reg.register(
            SkillManifest(
                skill_id="disabled_skill",
                name="禁用技能",
                description="",
                trigger_keywords=["代码"],
                enabled=False,
            )
        )

    def test_match_by_keyword(self) -> None:
        matched = self.reg.match_skills("怎么分析代码")
        assert len(matched) == 1
        assert matched[0].skill_id == "code"

    def test_no_match(self) -> None:
        matched = self.reg.match_skills("明天天气怎么样")
        assert len(matched) == 0

    def test_disabled_not_matched(self) -> None:
        matched = self.reg.match_skills("代码")
        assert all(s.skill_id != "disabled_skill" for s in matched)

    def test_merged_allowlist(self) -> None:
        tools = self.reg.get_merged_allowlist("代码分析")
        assert tools is not None
        assert "read_file" in tools
        assert "search_codebase" in tools

    def test_no_allowlist_if_no_skill(self) -> None:
        tools = self.reg.get_merged_allowlist("你好")
        assert tools is None  # 没有匹配的 skill → 无白名单限制

    def test_prompt_addons(self) -> None:
        addons = self.reg.get_prompt_addons("代码分析")
        assert len(addons) == 1
        assert addons[0] == "分析代码。"

    def test_list_enabled(self) -> None:
        skills = self.reg.list_enabled()
        assert len(skills) == 2  # code + general

    def test_get_skill_by_id(self) -> None:
        s = self.reg.get("code")
        assert s is not None
        assert s.name == "代码助手"


# ──────────────────────────────────────────────────────────────────────────────
# RegistryService
# ──────────────────────────────────────────────────────────────────────────────

class TestRegistryService:
    """RegistryService 统一接口验证。"""

    def test_tool_check(self) -> None:
        svc = build_registry_service(_make_settings())
        svc.tool_registry.register(ToolDefinition(name="search", description="", input_schema={}))
        ok, _ = svc.check_tool("search")
        assert ok is True

    def test_tool_reject_unregistered(self) -> None:
        svc = build_registry_service(_make_settings())
        ok, reason = svc.check_tool("nonexistent")
        assert ok is False
        assert reason == "tool_not_found"

    def test_rag_collection_check(self) -> None:
        svc = build_registry_service(_make_settings())
        svc.rag_registry.register(RagCollection(collection_id="foo", description=""))
        assert svc.check_collection("foo") is True
        assert svc.check_collection("bar") is False

    def test_skills_allowlist_integration(self) -> None:
        svc = build_registry_service(_make_settings())
        # 先在 tool_registry 中注册，否则白名单检查时工具不存在也会拒绝
        svc.tool_registry.register(
            ToolDefinition(name="tool_a", description="", input_schema={})
        )
        svc.tool_registry.register(
            ToolDefinition(name="tool_b", description="", input_schema={})
        )
        svc.skill_registry.register(
            SkillManifest(
                skill_id="test_skill",
                name="Test",
                description="",
                trigger_keywords=["测试"],
                tools_allowlist=["tool_a"],
            )
        )
        svc.set_allowlist_from_query("如何测试")
        ok, reason = svc.check_tool("tool_a")
        assert ok is True
        ok2, reason2 = svc.check_tool("tool_b")
        assert ok2 is False
        assert reason2 == "tool_not_in_allowlist"


def test_build_registry_auto_read_skill_when_skills_bundle_enabled(tmp_path) -> None:
    from backend.config_loader import (
        EmbeddingConfig,
        GenerationConfig,
        ModelsConfig,
        OpenAgentSettings,
        SkillsBundleConfig,
        StorageConfig,
        TokenizationConfig,
    )

    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
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
        storage=StorageConfig(sqlite_path=str(tmp_path / "reg.db")),
        tokenization=TokenizationConfig(provider="auto"),
        tools=[],
        skills_bundle=SkillsBundleConfig(enabled=True, skills_dir=str(skill_dir)),
        skills=[],
    )
    svc = build_registry_service(settings)
    t = svc.tool_registry.get("read_skill_reference")
    assert t is not None and t.enabled is True


def _make_settings():
    """构造一个最小 OpenAgentSettings，不依赖外部配置。"""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from backend.config_loader import OpenAgentSettings

    settings = MagicMock(spec=OpenAgentSettings)
    settings.tools = []
    settings.skills = []
    settings.skills_bundle = SimpleNamespace(
        enabled=False, skills_dir="skills", tool_name_aliases={}
    )
    settings.rag = MagicMock()
    settings.rag.views = []
    settings.storage = MagicMock()
    settings.storage.qdrant = MagicMock()
    settings.storage.qdrant.collection_name = "openagent_chunks"
    # Provide rag.allowed_origin_types for RetrievalService
    settings.rag.allowed_origin_types = None
    settings.evidence = MagicMock()
    settings.evidence.max_evidence_entry_tokens = 300
    return settings


# ──────────────────────────────────────────────────────────────────────────────
# 配置可加载测试
# ──────────────────────────────────────────────────────────────────────────────

class TestConfigLoading:
    """验证 openagent.yaml 中 tools / skills 段能被 pydantic 正常加载。"""

    def test_settings_has_tools_skills(self) -> None:
        """加载配置后，tools 和 skills 字段存在且可正常解析。"""
        from backend.config_loader import load_config

        cfg = load_config()
        # load_config 应成功（至少无报错）
        assert hasattr(cfg, "tools")
        assert hasattr(cfg, "skills")

    def test_mock_settings_tools_skills(self) -> None:
        settings = _make_settings()
        assert settings.tools == []
        assert settings.skills == []


# ──────────────────────────────────────────────────────────────────────────────
# P6 集成测试：tool_loop + registry 对接
# ──────────────────────────────────────────────────────────────────────────────

class TestToolLoopWithRegistry:
    """验证 tool_loop 与 ToolGateway 对接后正常工作。"""

    def test_tool_loop_gw_rejects_unregistered(self) -> None:
        """未注册工具 → 拒绝。"""
        from backend.kernel.blackboard import Blackboard
        from backend.kernel.budget import Budget
        from backend.registry.tool_gateway import ToolGateway
        from backend.runners.tool_loop import run_tool_loop_round

        reg = ToolRegistry()
        reg.register(ToolDefinition(name="echo", description="", input_schema={}))
        gw = ToolGateway(reg)
        reg.set_allowlist(["echo"])  # 只允许 echo

        blackboard = Blackboard()
        budget = Budget(max_tool_rounds=3)

        tool_calls = [{"id": "tc1", "function": {"name": "unknown", "arguments": "{}"}}]
        results = run_tool_loop_round(
            budget=budget,
            blackboard=blackboard,
            gateway=gw,
            tool_calls=tool_calls,
        )
        assert len(results) == 1
        assert results[0]["result"] is False
        assert results[0]["code"] == "tool_not_found"

    def test_tool_loop_gw_accepts_registered(self) -> None:
        """已注册且在白名单内 → 执行成功。"""
        from backend.kernel.blackboard import Blackboard
        from backend.kernel.budget import Budget
        from backend.registry.tool_gateway import ToolGateway
        from backend.runners.tool_loop import run_tool_loop_round

        reg = ToolRegistry()
        reg.register(ToolDefinition(name="add", description="", input_schema={}))
        gw = ToolGateway(reg)
        gw.register_handler("add", lambda a=0, b=0: a + b)

        blackboard = Blackboard()
        budget = Budget(max_tool_rounds=3)

        import json
        tool_calls = [{"id": "tc1", "function": {"name": "add", "arguments": json.dumps({"a": 3, "b": 4})}}]
        results = run_tool_loop_round(
            budget=budget,
            blackboard=blackboard,
            gateway=gw,
            tool_calls=tool_calls,
        )
        assert len(results) == 1
        assert results[0]["result"] is True
        assert results[0]["payload"] == 7
