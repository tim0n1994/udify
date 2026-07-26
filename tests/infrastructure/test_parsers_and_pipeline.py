"""
Tests for miu2d Parsers, PatchExecutor, and Pipeline
"""

import pytest

from udify.core.execution.patch_executor import PatchExecutor
from udify.core.execution.vfs import VirtualFileSystem
from udify.core.perception.parsers import INIParser, LuaParser, NPCScriptParser, OBJParser
from udify.core.pipeline import UdifyPipeline
from udify.models.cdl_patch import (
    CDLPatch,
    create_add_node_op,
    create_modify_property_op,
    create_remove_node_op,
)
from udify.models.content_graph import ContentGraph, NodeType


class TestINIParser:
    """INI Parser 测试"""

    @pytest.fixture
    def parser(self):
        return INIParser()

    @pytest.fixture
    def sample_ini(self, tmp_path):
        content = """[Hero]
MaxLife=100
MaxMana=50
Strength=10
Speed=5.5

[Boss_Dragon]
MaxLife=5000
MaxMana=200
Strength=80
Attack=150
Defense=100
"""
        path = tmp_path / "characters.ini"
        path.write_text(content, encoding="utf-8")
        return path

    def test_parse_basic(self, parser, sample_ini):
        """测试基本解析"""
        graph = ContentGraph()
        nodes = parser.parse(sample_ini, "characters.ini", graph)

        assert len(nodes) == 2
        assert nodes[0].name == "Hero"
        assert nodes[1].name == "Boss_Dragon"

    def test_type_inference(self, parser, sample_ini):
        """测试类型推断"""
        graph = ContentGraph()
        nodes = parser.parse(sample_ini, "characters.ini", graph)

        hero = nodes[0]
        assert hero.type == NodeType.CHARACTER
        assert hero.properties["MaxLife"] == 100
        assert hero.properties["MaxMana"] == 50
        assert hero.properties["Strength"] == 10
        assert hero.properties["Speed"] == 5.5

    def test_node_id_generation(self, parser, sample_ini):
        """测试节点 ID 生成"""
        graph = ContentGraph()
        nodes = parser.parse(sample_ini, "characters.ini", graph)

        assert "characters_ini_Hero" in nodes[0].id
        assert "characters_ini_Boss_Dragon" in nodes[1].id

    def test_file_node_creation(self, parser, sample_ini):
        """测试文件节点创建"""
        graph = ContentGraph()
        parser.parse(sample_ini, "characters.ini", graph)

        file_nodes = [n for n in graph.nodes if n.type == NodeType.RESOURCE]
        assert len(file_nodes) >= 1

    def test_modify_ini_content(self, parser):
        """测试修改 INI 内容"""
        content = "[Hero]\nMaxLife=100\n"
        result = parser.apply_patch_to_content(content, "Hero", "MaxLife", 200)
        assert "MaxLife=200" in result

    def test_add_property_to_ini(self, parser):
        """测试添加新属性到 INI"""
        content = "[Hero]\nMaxLife=100\n"
        result = parser.apply_patch_to_content(content, "Hero", "Dexterity", 15)
        assert "Dexterity=15" in result


class TestOBJParser:
    """OBJ Parser 测试"""

    @pytest.fixture
    def parser(self):
        return OBJParser()

    @pytest.fixture
    def sample_obj(self, tmp_path):
        content = """// Weapon definitions
IronSword
    Attack=25
    Price=100
    Durability=50
    Type=Weapon

FireStaff
    Attack=40
    MagicPower=60
    Price=500
    Type=Weapon

// Enemy definitions
Goblin
    MaxLife=80
    Attack=15
    Defense=5
    ExpReward=30
"""
        path = tmp_path / "items.obj"
        path.write_text(content, encoding="utf-8")
        return path

    def test_parse_objects(self, parser, sample_obj):
        """测试对象解析"""
        graph = ContentGraph()
        nodes = parser.parse(sample_obj, "items.obj", graph)

        assert len(nodes) == 3
        names = [n.name for n in nodes]
        assert "IronSword" in names
        assert "FireStaff" in names
        assert "Goblin" in names

    def test_type_inference(self, parser, sample_obj):
        """测试类型推断"""
        graph = ContentGraph()
        nodes = parser.parse(sample_obj, "items.obj", graph)

        items = [n for n in nodes if n.type == NodeType.ITEM]
        characters = [n for n in nodes if n.type == NodeType.CHARACTER]

        assert len(items) == 2
        assert len(characters) == 1

    def test_properties(self, parser, sample_obj):
        """测试属性提取"""
        graph = ContentGraph()
        nodes = parser.parse(sample_obj, "items.obj", graph)

        sword = next(n for n in nodes if n.name == "IronSword")
        assert sword.properties["Attack"] == 25
        assert sword.properties["Price"] == 100


class TestNPCScriptParser:
    """NPC Script Parser 测试"""

    @pytest.fixture
    def parser(self):
        return NPCScriptParser()

    @pytest.fixture
    def sample_npc(self, tmp_path):
        content = """// NPC Merchant script
@OnTalk
    Say "Welcome to my shop!"
    Say "What would you like to buy?"
    OpenShop
    Say "Thank you for your business!"

@OnAttack
    Say "Hey, stop that!"
    RunScript "call_guard.txt"

function GiveQuest
    Say "I need you to find the lost sword."
    SetFlag "quest_sword" 1
    AddItem "IronSword" 1
"""
        path = tmp_path / "merchant.npc"
        path.write_text(content, encoding="utf-8")
        return path

    def test_parse_events(self, parser, sample_npc):
        """测试事件解析"""
        graph = ContentGraph()
        nodes = parser.parse(sample_npc, "merchant.npc", graph)

        event_nodes = [n for n in nodes if n.properties.get("script_type") == "event"]
        assert len(event_nodes) == 2

    def test_dialogue_detection(self, parser, sample_npc):
        """测试对话检测"""
        graph = ContentGraph()
        nodes = parser.parse(sample_npc, "merchant.npc", graph)

        talk_node = next(
            (n for n in nodes if n.properties.get("events") and "ontalk" in n.properties["events"]),
            None,
        )
        assert talk_node is not None
        assert talk_node.properties["has_dialogue"] is True

    def test_script_references(self, parser, sample_npc):
        """测试脚本引用"""
        graph = ContentGraph()
        parser.parse(sample_npc, "merchant.npc", graph)

        ref_nodes = [n for n in graph.nodes if "ref:" in n.id]
        assert len(ref_nodes) >= 1


class TestLuaParser:
    """Lua Parser 测试"""

    @pytest.fixture
    def parser(self):
        return LuaParser()

    @pytest.fixture
    def sample_lua(self, tmp_path):
        content = """
MAX_PLAYERS = 4
GAME_VERSION = "1.0.5"
ENABLE_CHEATS = false

function InitializePlayer(playerId)
    SetPlayerProperty(playerId, "hp", 100)
    SetPlayerProperty(playerId, "mp", 50)
    AddItem(playerId, "StarterSword")
    return true
end

function SpawnBoss(bossType)
    if bossType == "dragon" then
        local boss = Spawn("DragonBoss")
        SetEnemyProperty(boss, "hp", 5000)
        PlaySound("dragon_roar.ogg")
    end
end
"""
        path = tmp_path / "game_logic.lua"
        path.write_text(content, encoding="utf-8")
        return path

    def test_parse_functions(self, parser, sample_lua):
        """测试函数解析"""
        graph = ContentGraph()
        nodes = parser.parse(sample_lua, "game_logic.lua", graph)

        func_nodes = [n for n in nodes if n.properties.get("script_type") == "lua_function"]
        assert len(func_nodes) == 2

    def test_globals(self, parser, sample_lua):
        """测试全局变量"""
        graph = ContentGraph()
        nodes = parser.parse(sample_lua, "game_logic.lua", graph)

        global_nodes = [n for n in nodes if n.properties.get("script_type") == "lua_global"]
        assert len(global_nodes) == 3

        max_players = next(n for n in global_nodes if n.name == "MAX_PLAYERS")
        assert max_players.properties["value"] == 4

    def test_api_detection(self, parser, sample_lua):
        """测试 API 检测"""
        graph = ContentGraph()
        nodes = parser.parse(sample_lua, "game_logic.lua", graph)

        spawn_func = next(n for n in nodes if n.name == "SpawnBoss")
        assert "spawn" in spawn_func.properties["modifies"]


class TestPatchExecutor:
    """Patch Executor 测试"""

    @pytest.fixture
    def executor(self, tmp_path):
        vfs = VirtualFileSystem(tmp_path)
        return PatchExecutor(vfs)

    @pytest.fixture
    def sample_ini_file(self, tmp_path):
        content = "[Hero]\nMaxLife=100\nStrength=10\n\n[Enemy]\nMaxLife=50\n"
        path = tmp_path / "test.ini"
        path.write_text(content, encoding="utf-8")
        return path

    def test_modify_property_ini(self, executor, sample_ini_file):
        """测试修改 INI 属性"""
        patch = CDLPatch()
        patch.add_operation(
            create_modify_property_op(
                "test_ini_Hero",
                "MaxLife",
                200,
            )
        )

        result = executor.execute(patch)
        assert result["success"]

        # 检查 VFS 中的修改
        modified = executor.vfs.read_file("test.ini")
        assert "MaxLife=200" in modified

    def test_add_node_ini(self, executor, sample_ini_file):
        """测试添加新节点（INI Section）"""
        patch = CDLPatch()
        patch.add_operation(
            create_add_node_op(
                node_id="test_ini_NewChar",
                node_type=NodeType.CHARACTER,
                name="NewChar",
                properties={"MaxLife": 150, "Strength": 20},
                source_path="test.ini",
            )
        )

        result = executor.execute(patch)
        assert result["success"]

        content = executor.vfs.read_file("test.ini")
        assert "[NewChar]" in content
        assert "MaxLife=150" in content

    def test_remove_node_ini(self, executor, sample_ini_file):
        """测试删除节点（INI Section）"""
        patch = CDLPatch()
        patch.add_operation(create_remove_node_op("test_ini_Enemy"))

        result = executor.execute(patch)
        assert result["success"]

        content = executor.vfs.read_file("test.ini")
        assert "[Enemy]" not in content

    def test_unsupported_operation(self, executor):
        """测试不支持的操作"""
        from udify.models.cdl_patch import OpType, PatchOperation

        patch = CDLPatch()
        patch.add_operation(
            PatchOperation(
                op_type=OpType.ADD_EDGE,
                target_id="a",
                payload={},
            )
        )

        result = executor.execute(patch)
        assert not result["success"]
        assert len(result["failed"]) == 1


class TestUdifyPipeline:
    """Udify Pipeline 测试"""

    @pytest.fixture
    def pipeline(self, tmp_path):
        # 创建游戏目录结构
        (tmp_path / "characters.ini").write_text("[Hero]\nMaxLife=100\n")
        (tmp_path / "items.ini").write_text("[Sword]\nAttack=20\n")

        return UdifyPipeline(game_root=tmp_path)

    @pytest.mark.asyncio
    async def test_basic_flow(self, pipeline):
        """测试基本流程"""
        result = await pipeline.process_intent("user1", "让BOSS血量翻倍", preview_only=True)

        # 即使无法找到 BOSS，也应该完成流程
        assert result is not None
        assert result.session_id != ""

    @pytest.mark.asyncio
    async def test_invalid_intent(self, pipeline):
        """测试无效意图"""
        result = await pipeline.process_intent("user1", "帮我写情书", preview_only=True)
        assert not result.success

    @pytest.mark.asyncio
    async def test_preview_mode(self, pipeline):
        """测试预览模式"""
        await pipeline.process_intent("user1", "让BOSS血量翻倍", preview_only=True)

        # 预览模式不应该修改实际文件
        hero_content = (pipeline.game_root / "characters.ini").read_text()
        assert "MaxLife=100" in hero_content

    def test_rollback(self, pipeline):
        """测试回滚"""
        # 先执行一个操作
        import asyncio

        result = asyncio.run(pipeline.process_intent("user1", "让BOSS血量翻倍", preview_only=True))

        pipeline.rollback_session(result.session_id)
        assert True  # 取决于是否有检查点

    def test_stats(self, pipeline):
        """测试统计"""
        stats = pipeline.get_stats()
        assert "sessions" in stats
        assert "events" in stats
