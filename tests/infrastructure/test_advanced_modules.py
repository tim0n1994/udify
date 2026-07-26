"""
Tests for Knowledge Graph, VFS, Sandbox, Feedback, Mod Manager, Enhanced Validator
"""

import pytest

from udify.core.execution import SandboxExecutor, VirtualFileSystem
from udify.core.feedback import FeedbackLoop
from udify.core.knowledge import GameKnowledgeGraph
from udify.core.mod_manager import (
    ModStatus,
    MultiModManager,
)
from udify.core.validation import EnhancedValidator


class TestGameKnowledgeGraph:
    """GameKnowledgeGraph 测试"""

    @pytest.fixture
    def kg(self):
        return GameKnowledgeGraph()

    def test_init(self, kg):
        """测试初始化"""
        summary = kg.get_knowledge_summary()
        assert summary["rule_count"] > 0
        assert summary["pattern_count"] > 0
        assert summary["dangerous_pattern_count"] > 0

    def test_validate_safe_operations(self, kg):
        """测试安全操作"""
        operations = [
            {
                "op_type": "MODIFY_INI",
                "target_id": "boss1",
                "payload": {"key": "MaxLife", "new_value": 500},
            },
        ]
        warnings = kg.validate_mod_against_knowledge(operations)
        # 500 在合理范围内
        assert not any(w.level == "critical" for w in warnings)

    def test_validate_dangerous_operations(self, kg):
        """测试危险操作"""
        operations = [
            {
                "op_type": "MODIFY_INI",
                "target_id": "boss1",
                "payload": {"key": "MaxLife", "value": 999999999},
            },
        ]
        warnings = kg.validate_mod_against_knowledge(operations)
        assert any(w.level == "error" for w in warnings)

    def test_detect_dangerous_pattern(self, kg):
        """测试危险模式检测"""
        operations = [
            {"op_type": "DELETE", "payload": {"pattern": "delete_all_enemies"}},
        ]
        warnings = kg.validate_mod_against_knowledge(operations)
        assert any(w.level == "critical" for w in warnings)

    def test_recommended_pattern(self, kg):
        """测试模式推荐"""
        pattern = kg.get_recommended_pattern("让游戏变困难")
        assert pattern is not None
        assert "困难" in pattern["description"] or "hard" in pattern["description"].lower()

    def test_npc_archetype(self, kg):
        """测试 NPC 原型"""
        archetype = kg.get_npc_archetype("first_boss")
        assert archetype is not None
        assert "hp" in archetype["typical_stats"]

    def test_map_region(self, kg):
        """测试地图区域"""
        region = kg.get_map_region("starter_village")
        assert region is not None
        assert region["level_range"][0] == 1

    def test_magic_combo(self, kg):
        """测试技能组合"""
        assert kg.is_valid_magic_combo("LineMove", "freeze")
        assert not kg.is_valid_magic_combo("InvalidMove", "freeze")

    def test_related_mechanics(self, kg):
        """测试相关机制"""
        relations = kg.get_related_mechanics("increase_boss_hp")
        assert len(relations) > 0
        assert any(r["effect"] == "increase_exp_reward" for r in relations)


class TestVirtualFileSystem:
    """VirtualFileSystem 测试"""

    @pytest.fixture
    def vfs(self, tmp_path):
        # 创建测试文件
        (tmp_path / "test.ini").write_text("[Main]\nHP=100\n")
        return VirtualFileSystem(tmp_path)

    def test_read_file(self, vfs):
        """测试读取文件"""
        content = vfs.read_file("test.ini")
        assert content is not None
        assert "HP=100" in content

    def test_write_file(self, vfs):
        """测试写入文件"""
        vfs.write_file("test.ini", "[Main]\nHP=200\n")
        content = vfs.read_file("test.ini")
        assert "HP=200" in content
        assert vfs._files["test.ini"].is_modified

    def test_new_file(self, vfs):
        """测试新文件"""
        vfs.write_file("new.txt", "new content")
        assert vfs._files["new.txt"].is_new
        assert vfs.read_file("new.txt") == "new content"

    def test_delete_file(self, vfs):
        """测试删除文件"""
        vfs.delete_file("test.ini")
        assert vfs._files["test.ini"].is_deleted
        assert vfs.read_file("test.ini") is None

    def test_diff(self, vfs):
        """测试 diff"""
        vfs.write_file("test.ini", "[Main]\nHP=200\n")
        diff = vfs.get_diff("test.ini")
        assert diff is not None
        assert diff["status"] == "modified"
        assert "HP=200" in diff["current"]

    def test_rollback(self, vfs):
        """测试回滚"""
        vfs.write_file("test.ini", "[Main]\nHP=200\n")
        vfs.rollback()
        assert len(vfs._files) == 0

    def test_apply_to_filesystem(self, vfs):
        """测试应用到实际文件系统"""
        vfs.write_file("test.ini", "[Main]\nHP=300\n")
        result = vfs.apply_to_filesystem()
        assert len(result["applied"]) > 0

        # 验证文件被修改
        content = (vfs.base_path / "test.ini").read_text()
        assert "HP=300" in content

    def test_stats(self, vfs):
        """测试统计"""
        vfs.write_file("test.ini", "modified")
        vfs.write_file("new.txt", "new")
        vfs.delete_file("missing.txt")

        stats = vfs.get_stats()
        assert stats["modified"] == 1
        assert stats["new"] == 1


class TestSandboxExecutor:
    """SandboxExecutor 测试"""

    @pytest.fixture
    def sandbox(self):
        return SandboxExecutor()

    def test_safe_script_validation(self, sandbox):
        """测试安全脚本验证"""
        code = "local x = 1 + 1\nreturn x"
        report = sandbox.validate_script_safety(code, "lua")
        assert report.is_safe

    def test_dangerous_script_validation(self, sandbox):
        """测试危险脚本验证"""
        code = "os.execute('rm -rf /')"
        report = sandbox.validate_script_safety(code, "lua")
        assert not report.is_safe
        assert any(v["type"] == "dangerous_pattern" for v in report.vulnerabilities)

    def test_network_operation_detection(self, sandbox):
        """测试网络操作检测"""
        code = "local socket = require('socket')"
        report = sandbox.validate_script_safety(code, "lua")
        assert any(v["type"] == "network_operation" for v in report.vulnerabilities)

    def test_path_traversal_detection(self, sandbox):
        """测试路径遍历检测"""
        code = "local f = io.open('../../../etc/passwd')"
        report = sandbox.validate_script_safety(code, "lua")
        assert any(v["type"] == "path_traversal" for v in report.vulnerabilities)

    def test_dsl_validation(self, sandbox):
        """测试 DSL 验证"""
        code = "Say Hello\nAddLife 100"
        report = sandbox.validate_script_safety(code, "dsl")
        assert report.is_safe


class TestFeedbackLoop:
    """FeedbackLoop 测试"""

    @pytest.fixture
    def loop(self):
        return FeedbackLoop()

    @pytest.mark.asyncio
    async def test_collect_feedback(self, loop):
        """测试收集反馈"""
        feedback = await loop.collect_feedback(
            session_id="s1",
            mod_id="m1",
            feedback_type="rating",
            content="这个Mod很好",
            rating=5,
        )
        assert feedback.feedback_id is not None
        assert feedback.rating == 5

    @pytest.mark.asyncio
    async def test_sentiment_analysis(self, loop):
        """测试情感分析"""
        positive = await loop.learning_engine.analyze_sentiment("非常好，很满意")
        assert positive > 0

        negative = await loop.learning_engine.analyze_sentiment("很差，不满意")
        assert negative < 0

    @pytest.mark.asyncio
    async def test_action_weight_update(self, loop):
        """测试动作权重更新"""
        await loop.learning_engine.update_action_weight(
            action_type="MODIFY_INI",
            target_type="CHARACTER",
            sentiment=0.8,
            rating=5,
        )

        key = "MODIFY_INI:CHARACTER"
        assert key in loop.learning_engine._action_weights
        assert loop.learning_engine._action_weights[key].success_count == 1

    def test_extract_keywords(self, loop):
        """测试关键词提取"""
        keywords = loop.learning_engine._extract_keywords("increase boss health and damage")
        assert "increase" in keywords
        assert "boss" in keywords
        assert "health" in keywords

    @pytest.mark.asyncio
    async def test_pattern_suggestions(self, loop):
        """测试模式推荐"""
        suggestions = await loop.get_suggestions("困难模式")
        # 初始时可能没有模式，但至少不会报错
        assert isinstance(suggestions, list)


class TestMultiModManager:
    """MultiModManager 测试"""

    @pytest.fixture
    def manager(self):
        return MultiModManager("/tmp/game")

    @pytest.mark.asyncio
    async def test_install_mod(self, manager):
        """测试安装 Mod"""
        result = await manager.install_mod(
            mod_id="mod1",
            name="Hard Mode",
            version="1.0.0",
            author="test",
            files=["config.ini", "boss_stats.ini"],
        )
        assert result.success
        assert result.mod_id == "mod1"

    @pytest.mark.asyncio
    async def test_install_with_dependency(self, manager):
        """测试带依赖安装"""
        await manager.install_mod(
            mod_id="base_mod",
            name="Base",
            version="1.0.0",
            author="test",
            files=["base.ini"],
        )

        result = await manager.install_mod(
            mod_id="dependent_mod",
            name="Dependent",
            version="1.0.0",
            author="test",
            files=["dependent.ini"],
            dependencies=["base_mod"],
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_install_missing_dependency(self, manager):
        """测试缺少依赖"""
        result = await manager.install_mod(
            mod_id="mod1",
            name="Test",
            version="1.0.0",
            author="test",
            files=["test.ini"],
            dependencies=["missing_mod"],
        )
        assert not result.success
        assert any("缺少依赖" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_file_conflict(self, manager):
        """测试文件冲突"""
        await manager.install_mod(
            mod_id="mod1",
            name="Mod1",
            version="1.0.0",
            author="test",
            files=["shared.ini"],
        )

        result = await manager.install_mod(
            mod_id="mod2",
            name="Mod2",
            version="1.0.0",
            author="test",
            files=["shared.ini"],
        )
        assert not result.success
        assert len(result.conflicts) > 0

    @pytest.mark.asyncio
    async def test_uninstall_mod(self, manager):
        """测试卸载 Mod"""
        await manager.install_mod(
            mod_id="mod1",
            name="Mod1",
            version="1.0.0",
            author="test",
            files=["test.ini"],
        )

        result = await manager.uninstall_mod("mod1")
        assert result.success
        assert "mod1" not in manager._installed

    @pytest.mark.asyncio
    async def test_enable_disable(self, manager):
        """测试启用/禁用"""
        await manager.install_mod(
            mod_id="mod1",
            name="Mod1",
            version="1.0.0",
            author="test",
            files=["test.ini"],
        )

        assert await manager.disable_mod("mod1")
        assert manager._installed["mod1"].status == ModStatus.DISABLED

        assert await manager.enable_mod("mod1")
        assert manager._installed["mod1"].status == ModStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_mod_stack(self, manager):
        """测试 Mod 堆栈"""
        await manager.install_mod("mod1", "M1", "1.0", "a", ["f1.ini"])
        await manager.install_mod("mod2", "M2", "1.0", "a", ["f2.ini"])

        stack = await manager.create_mod_stack()
        assert len(stack.mods) == 2
        assert len(stack.load_order) == 2

    @pytest.mark.asyncio
    async def test_topological_sort(self, manager):
        """测试拓扑排序"""
        await manager.install_mod("base", "Base", "1.0", "a", ["b.ini"])
        await manager.install_mod("ext", "Ext", "1.0", "a", ["e.ini"], dependencies=["base"])

        stack = await manager.create_mod_stack()
        assert stack.load_order[0] == "base"
        assert stack.load_order[1] == "ext"

    def test_stats(self, manager):
        """测试统计"""
        stats = manager.get_stats()
        assert "total_mods" in stats
        assert "status_breakdown" in stats


class TestEnhancedValidator:
    """EnhancedValidator 测试"""

    @pytest.fixture
    def validator(self):
        return EnhancedValidator()

    @pytest.mark.asyncio
    async def test_valid_patch(self, validator):
        """测试有效 Patch"""
        from udify.models.cdl_patch import CDLPatch, create_modify_property_op

        patch = CDLPatch()
        patch.add_operation(create_modify_property_op("boss1", "hp", 200))

        report = await validator.validate(patch)
        assert report.is_valid

    @pytest.mark.asyncio
    async def test_invalid_numeric_patch(self, validator):
        """测试无效数值 Patch"""
        from udify.models.cdl_patch import CDLPatch, create_modify_property_op

        patch = CDLPatch()
        patch.add_operation(create_modify_property_op("boss1", "MaxLife", -100))

        report = await validator.validate(patch)
        assert not report.is_valid
        assert any(
            "1-999999" in w.message or "范围" in w.message for w in report.knowledge_warnings
        )

    @pytest.mark.asyncio
    async def test_knowledge_warning(self, validator):
        """测试知识警告"""
        from udify.models.cdl_patch import CDLPatch, create_modify_property_op

        patch = CDLPatch()
        patch.add_operation(create_modify_property_op("boss1", "MaxLife", 99999999))

        report = await validator.validate(patch)
        assert any(w.level == "error" for w in report.knowledge_warnings)

    @pytest.mark.asyncio
    async def test_safety_validation(self, validator):
        """测试安全验证"""
        from udify.models.cdl_patch import CDLPatch, OpType, PatchOperation

        patch = CDLPatch()
        patch.add_operation(
            PatchOperation(
                op_type=OpType.MODIFY_PROPERTY,
                target_id="script1",
                payload={"code": "os.execute('bad')", "language": "lua"},
            )
        )

        report = await validator.validate(patch)
        assert not report.is_valid or (
            report.safety_report is not None and not report.safety_report.is_safe
        )

    def test_knowledge_summary(self, validator):
        """测试知识摘要"""
        summary = validator.get_knowledge_summary()
        assert summary["rule_count"] > 0
        assert summary["pattern_count"] > 0
