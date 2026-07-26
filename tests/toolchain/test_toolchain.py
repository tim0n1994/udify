"""
工具链（Toolchain）测试。

覆盖：
- 工具注册与可用性检测（所有社区工具在本机未安装时降级）
- get_tool_for_game 的引擎过滤
- extract_assets 在无工具时的降级路径
- check_mod_compatibility 的 manifest 读取
- migrate_mod 未实现占位
- Secure Tool Gateway 集成（ITERATION-PLAN §4.3 首个迁移目标）

对应 ITERATION-PLAN-2026-07.md §9.2「工具不可用时的降级路径也要测」。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from udify.core.tool_gateway import (
    RiskLevel,
    ToolAuditChain,
    ToolGateway,
    ToolPolicy,
)
from udify.core.toolchain import ToolchainManager


@pytest.fixture
def manager() -> ToolchainManager:
    return ToolchainManager()


class TestToolRegistry:
    """工具注册与发现"""

    def test_known_tools_loaded(self, manager: ToolchainManager) -> None:
        """KNOWN_TOOLS 应包含核心工具"""
        for tool_id in ["assetstudio", "miu2d_converter", "dnspy", "frida"]:
            assert tool_id in manager.tools

    def test_tool_availability_flag_exists(self, manager: ToolchainManager) -> None:
        """每个工具应有 available 标志（True/False）"""
        for tool in manager.tools.values():
            assert "available" in tool
            assert isinstance(tool["available"], bool)

    def test_get_tool_for_unity(self, manager: ToolchainManager) -> None:
        """Unity 引擎应能匹配到 AssetStudio/UABE（无论是否安装）"""
        # 注意：未安装时返回空列表是正确的降级
        tools = manager.get_tool_for_game("Unity")
        # 只有 available=True 才返回；本机无工具时应为空
        assert isinstance(tools, list)
        for t in tools:
            assert "Unity" in t["supported_games"] or "Generic" in t["supported_games"]

    def test_get_tool_for_miu2d(self, manager: ToolchainManager) -> None:
        tools = manager.get_tool_for_game("miu2d")
        assert isinstance(tools, list)


class TestExtractAssetsDegradation:
    """资源提取的降级路径"""

    def test_extract_no_tools_returns_error(
        self, manager: ToolchainManager, tmp_path: Path
    ) -> None:
        """无可用工具时应返回结构化错误，而非抛异常"""
        result = manager.extract_assets("miu2d", tmp_path, tmp_path / "out")
        # 本机未安装 miu2d-converter
        assert result["success"] is False
        assert "error" in result or "tools_needed" in result

    def test_extract_unknown_engine(self, manager: ToolchainManager, tmp_path: Path) -> None:
        """未知引擎也应优雅降级"""
        result = manager.extract_assets("nonexistent_engine", tmp_path, tmp_path / "out")
        assert result["success"] is False


class TestModCompatibility:
    """Mod 兼容性检查"""

    def test_compatible_manifest(self, manager: ToolchainManager, tmp_path: Path) -> None:
        """manifest 支持当前版本 → compatible"""
        (tmp_path / "manifest.json").write_text(
            json.dumps({"version": "1.0.0", "supported_versions": ["1.0", "1.1"]})
        )
        result = manager.check_mod_compatibility(tmp_path, "1.0")
        assert result["compatible"] is True

    def test_incompatible_version(self, manager: ToolchainManager, tmp_path: Path) -> None:
        """manifest 不支持当前版本 → incompatible"""
        (tmp_path / "manifest.json").write_text(
            json.dumps({"version": "1.0.0", "supported_versions": ["1.0"]})
        )
        result = manager.check_mod_compatibility(tmp_path, "2.0")
        assert result["compatible"] is False
        assert any("2.0" in e for e in result["errors"])

    def test_no_manifest_defaults_compatible(
        self, manager: ToolchainManager, tmp_path: Path
    ) -> None:
        """无 manifest 默认兼容"""
        result = manager.check_mod_compatibility(tmp_path, "1.0")
        assert result["compatible"] is True
        assert result["mod_version"] == "unknown"


class TestMigrateMod:
    """Mod 迁移（占位实现）"""

    def test_migrate_not_implemented(self, manager: ToolchainManager, tmp_path: Path) -> None:
        """迁移功能未实现应返回 success=False 而非抛异常"""
        result = manager.migrate_mod(tmp_path, "1.0", "2.0")
        assert result["success"] is False
        assert "from_version" in result
        assert "to_version" in result


class TestGatewayIntegration:
    """Secure Tool Gateway 集成（ITERATION-PLAN §4.3：首个迁移目标 miu2d converter）"""

    def test_miu2d_converter_routed_through_gateway(self, tmp_path: Path) -> None:
        """注入 gateway 后，miu2d converter 调用走网关（R3，需沙箱/确认 → 被拦）"""
        game_root = tmp_path / "game"
        game_root.mkdir()
        gw = ToolGateway(
            policy=ToolPolicy(allowed_roots=[game_root]),
            audit=ToolAuditChain(),
        )
        mgr = ToolchainManager(gateway=gw)
        result = mgr._run_miu2d_converter(game_root, tmp_path / "out", None)
        # run_external_tool 是 R3，require_confirmation_above=R3 → 需人工确认 → 被 gateway 拦
        assert result["success"] is False
        assert "blocked_reason" in result
        # 审计链记录了这次拦截
        assert len(gw.audit.records()) == 1
        assert gw.audit.records()[0].risk == RiskLevel.R3.name

    def test_no_gateway_keeps_legacy_behavior(
        self, manager: ToolchainManager, tmp_path: Path
    ) -> None:
        """未注入 gateway 时保持旧行为（向后兼容）"""
        result = manager._run_miu2d_converter(tmp_path, tmp_path / "out", None)
        # 工具未安装 → 旧路径返回 success=False（无 blocked_reason 字段）
        assert result["success"] is False
        assert "blocked_reason" not in result
