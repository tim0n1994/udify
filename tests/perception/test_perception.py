"""
Tests for Perception Engine

测试感知引擎的各个组件：
1. 引擎检测器
2. 资源提取器
3. 机制分析器
4. 完整感知流程
"""

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest

from udify.core.perception import PerceptionEngine, perceive_content
from udify.core.perception.engine_detector import (
    CompositeEngineDetector,
    GodotDetector,
    RPGMakerDetector,
    UnityDetector,
    UnrealDetector,
    detect_engine,
)
from udify.core.perception.mechanism_analyzer import (
    CompositeMechanismAnalyzer,
    RPGMakerMechanismAnalyzer,
    UnityMechanismAnalyzer,
    analyze_mechanisms,
)
from udify.core.perception.resource_extractor import (
    CompositeResourceExtractor,
    extract_resources,
)
from udify.models.content_graph import (
    ContentGraph,
    GameEngine,
    MediaType,
    NodeType,
)


class TestUnityDetector:
    """Unity 引擎检测器测试"""
    
    @pytest.fixture
    def unity_game_dir(self, tmp_path: Path):
        """创建模拟 Unity 游戏目录"""
        # Windows 风格
        game_dir = tmp_path / "MyGame"
        data_dir = game_dir / "MyGame_Data"
        data_dir.mkdir(parents=True)
        
        # 创建特征文件
        (data_dir / "globalgamemanagers").write_bytes(b"UnityFS\x05\x00\x00\x00" + b"\x00" * 100)
        (data_dir / "level0").write_bytes(b"\x00" * 64)
        (data_dir / "sharedassets0.assets").write_bytes(b"\x00" * 64)
        
        managed_dir = data_dir / "Managed"
        managed_dir.mkdir()
        (managed_dir / "UnityEngine.dll").write_text("dummy")
        
        return game_dir
    
    @pytest.fixture
    def unity_macos_app(self, tmp_path: Path):
        """创建模拟 Unity macOS app bundle"""
        app_dir = tmp_path / "MyGame.app"
        data_dir = app_dir / "Contents" / "Resources" / "Data"
        data_dir.mkdir(parents=True)
        
        (data_dir / "globalgamemanagers").write_bytes(b"UnityFS\x05\x00\x00\x00" + b"\x00" * 100)
        
        return app_dir
    
    @pytest.fixture
    def unity_apk(self, tmp_path: Path):
        """创建模拟 Unity APK"""
        apk_path = tmp_path / "game.apk"
        
        with zipfile.ZipFile(apk_path, 'w') as zf:
            zf.writestr("assets/bin/Data/Managed/UnityEngine.dll", "dummy")
            zf.writestr("assets/bin/Data/globalgamemanagers", "dummy")
            zf.writestr("classes.dex", "dummy")
        
        return apk_path
    
    def test_detect_unity_windows(self, unity_game_dir: Path):
        """测试检测 Windows 版 Unity 游戏"""
        detector = UnityDetector()
        result = detector.detect(unity_game_dir)
        
        assert result is not None
        assert result.engine == GameEngine.UNITY
        assert result.confidence > 0.5
        assert any("globalgamemanagers" in e for e in result.evidence)
    
    def test_detect_unity_macos(self, unity_macos_app: Path):
        """测试检测 macOS 版 Unity 游戏"""
        detector = UnityDetector()
        result = detector.detect(unity_macos_app)
        
        assert result is not None
        assert result.engine == GameEngine.UNITY
        assert result.confidence > 0.5
    
    def test_detect_unity_apk(self, unity_apk: Path):
        """测试检测 Unity APK"""
        detector = UnityDetector()
        result = detector.detect(unity_apk)
        
        assert result is not None
        assert result.engine == GameEngine.UNITY
        assert result.confidence > 0.5
    
    def test_not_unity(self, tmp_path: Path):
        """测试非 Unity 目录"""
        non_unity_dir = tmp_path / "NotAGame"
        non_unity_dir.mkdir()
        (non_unity_dir / "readme.txt").write_text("This is not a game")
        
        detector = UnityDetector()
        result = detector.detect(non_unity_dir)
        
        assert result is None


class TestUnrealDetector:
    """Unreal 引擎检测器测试"""
    
    @pytest.fixture
    def unreal_game_dir(self, tmp_path: Path):
        """创建模拟 Unreal 游戏目录"""
        game_dir = tmp_path / "UnrealGame"
        game_dir.mkdir()
        
        # .pak 文件
        pak_file = game_dir / "Content.pak"
        pak_file.write_bytes(struct.pack('<I', 0x5A6F12E1) + b"\x00" * 100)
        
        return game_dir
    
    @pytest.fixture
    def unreal_project_dir(self, tmp_path: Path):
        """创建模拟 Unreal 源码项目"""
        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()
        
        uproject = project_dir / "MyProject.uproject"
        uproject.write_text(json.dumps({
            "EngineAssociation": "5.2",
            "Category": "",
            "Description": "",
        }))
        
        content_dir = project_dir / "Content"
        content_dir.mkdir()
        
        return project_dir
    
    def test_detect_unreal_pak(self, unreal_game_dir: Path):
        """测试检测 Unreal pak 文件"""
        detector = UnrealDetector()
        result = detector.detect(unreal_game_dir)
        
        assert result is not None
        assert result.engine == GameEngine.UNREAL
        assert result.confidence > 0.5
    
    def test_detect_unreal_uproject(self, unreal_project_dir: Path):
        """测试检测 Unreal 项目文件"""
        detector = UnrealDetector()
        result = detector.detect(unreal_project_dir)
        
        assert result is not None
        assert result.engine == GameEngine.UNREAL
        assert result.version == "5.2"
        assert result.confidence > 0.5


class TestGodotDetector:
    """Godot 引擎检测器测试"""
    
    @pytest.fixture
    def godot_project_dir(self, tmp_path: Path):
        """创建模拟 Godot 项目目录"""
        project_dir = tmp_path / "GodotGame"
        project_dir.mkdir()
        
        project_file = project_dir / "project.godot"
        project_file.write_text("""
; Engine Configuration File.
; Godot version: 4.1

[application]
config/name="My Game"
config/features=PackedStringArray("4.1", "Mobile")
        """)
        
        # 创建场景文件
        scene_file = project_dir / "main.tscn"
        scene_file.write_text("[gd_scene load_steps=1 format=3]\n")
        
        # 创建脚本
        script_file = project_dir / "player.gd"
        script_file.write_text("extends CharacterBody2D\n")
        
        return project_dir
    
    @pytest.fixture
    def godot_pck_file(self, tmp_path: Path):
        """创建模拟 Godot pck 文件"""
        pck_file = tmp_path / "game.pck"
        pck_file.write_bytes(b"GDPC" + b"\x00" * 100)
        return pck_file
    
    def test_detect_godot_project(self, godot_project_dir: Path):
        """测试检测 Godot 项目"""
        detector = GodotDetector()
        result = detector.detect(godot_project_dir)
        
        assert result is not None
        assert result.engine == GameEngine.GODOT
        assert result.confidence > 0.5
    
    def test_detect_godot_pck(self, godot_pck_file: Path):
        """测试检测 Godot pck 文件"""
        detector = GodotDetector()
        result = detector.detect(godot_pck_file)
        
        assert result is not None
        assert result.engine == GameEngine.GODOT
        assert result.confidence > 0.5


class TestRPGMakerDetector:
    """RPG Maker 引擎检测器测试"""
    
    @pytest.fixture
    def rpgmv_project_dir(self, tmp_path: Path):
        """创建模拟 RPG Maker MV 项目"""
        project_dir = tmp_path / "RPGMVGame"
        
        # www 目录结构
        www_dir = project_dir / "www"
        www_dir.mkdir(parents=True)
        (www_dir / "index.html").write_text("<html></html>")
        js_dir = www_dir / "js"
        js_dir.mkdir(parents=True)
        (js_dir / "plugins.js").write_text("var $plugins = []")
        
        # data 目录
        data_dir = www_dir / "data"
        data_dir.mkdir(parents=True)
        
        system_json = data_dir / "System.json"
        system_json.write_text(json.dumps({
            "gameTitle": "My RPG",
            "versionId": 12345,
        }))
        
        return project_dir
    
    @pytest.fixture
    def rpgvx_project_dir(self, tmp_path: Path):
        """创建模拟 RPG Maker VX Ace 项目"""
        project_dir = tmp_path / "RPGVXGame"
        project_dir.mkdir()
        
        (project_dir / "Game.exe").write_bytes(b"MZ\x00\x00")
        (project_dir / "Game.ini").write_text("[Game]\nLibrary=RGSS300.dll\n")
        
        data_dir = project_dir / "Data"
        data_dir.mkdir()
        (data_dir / "System.rvdata2").write_bytes(b"\x00" * 64)
        
        return project_dir
    
    def test_detect_rpgmv(self, rpgmv_project_dir: Path):
        """测试检测 RPG Maker MV"""
        detector = RPGMakerDetector()
        result = detector.detect(rpgmv_project_dir)
        
        assert result is not None
        assert result.engine == GameEngine.RPG_MAKER
        assert result.confidence > 0.5
    
    def test_detect_rpgvx(self, rpgvx_project_dir: Path):
        """测试检测 RPG Maker VX Ace"""
        detector = RPGMakerDetector()
        result = detector.detect(rpgvx_project_dir)
        
        assert result is not None
        assert result.engine == GameEngine.RPG_MAKER
        assert result.confidence > 0.5


class TestCompositeEngineDetector:
    """组合引擎检测器测试"""
    
    def test_detect_best_match(self, tmp_path: Path):
        """测试从多个候选中选择最佳匹配"""
        # 创建一个目录，同时有 Unity 和 Godot 的特征
        #（虽然现实中不会发生，但测试选择逻辑）
        game_dir = tmp_path / "AmbiguousGame"
        data_dir = game_dir / "Game_Data"
        data_dir.mkdir(parents=True)
        
        # Unity 特征（置信度 ~0.6）
        (data_dir / "globalgamemanagers").write_bytes(b"UnityFS\x05\x00\x00\x00" + b"\x00" * 100)
        
        # Godot 特征（project.godot 是强信号，置信度 0.9）
        (game_dir / "project.godot").write_text("[application]\n")
        
        detector = CompositeEngineDetector()
        result = detector.detect(game_dir)
        
        # Godot 的 project.godot 是更强的信号（0.9），应该被选为最佳匹配
        # 同时结果中应该包含关于 Unity 的警告
        assert result.engine == GameEngine.GODOT
        assert result.confidence > 0.5
        assert any("Alternative detected" in e for e in result.evidence)


class TestUnityResourceExtractor:
    """Unity 资源提取器测试"""
    
    @pytest.fixture
    def unity_game_with_assets(self, tmp_path: Path):
        """创建带资源的 Unity 游戏目录"""
        game_dir = tmp_path / "UnityGame"
        data_dir = game_dir / "UnityGame_Data"
        data_dir.mkdir(parents=True)
        
        # 创建资源目录
        textures_dir = data_dir / "Resources" / "Textures"
        textures_dir.mkdir(parents=True)
        
        # 创建 PNG 文件（有效的 PNG 头）
        png_file = textures_dir / "player.png"
        png_file.write_bytes(
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR"  # IHDR chunk
            b"\x00\x00\x00\x10"  # width: 16
            b"\x00\x00\x00\x10"  # height: 16
            b"\x08\x02\x00\x00\x00"
            b"\x90\x91h\x6b"  # CRC
        )
        
        # 创建音频文件
        audio_dir = data_dir / "Resources" / "Audio"
        audio_dir.mkdir(parents=True)
        (audio_dir / "bgm.wav").write_bytes(b"RIFF" + b"\x00" * 100)
        
        # 创建脚本
        scripts_dir = data_dir / "Managed"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "Assembly-CSharp.dll").write_bytes(b"MZ" + b"\x00" * 100)
        
        return game_dir
    
    def test_extract_unity_resources(self, unity_game_with_assets: Path):
        """测试提取 Unity 资源"""
        extractor = CompositeResourceExtractor()
        result = extractor.extract(unity_game_with_assets, GameEngine.UNITY)
        
        assert result.success
        assert len(result.assets) > 0
        
        # 检查是否有纹理
        textures = [a for a in result.assets if a.type == 'texture']
        assert len(textures) > 0
        
        # 检查 PNG 尺寸是否正确解析
        png_asset = [a for a in textures if a.format == 'png']
        if png_asset:
            assert png_asset[0].width == 16
            assert png_asset[0].height == 16
        
        # 检查音频
        audio = [a for a in result.assets if a.type == 'audio']
        assert len(audio) > 0


class TestRPGMakerMechanismAnalyzer:
    """RPG Maker 机制分析器测试"""
    
    @pytest.fixture
    def rpgmv_game_with_data(self, tmp_path: Path):
        """创建带数据文件的 RPG Maker MV 游戏"""
        project_dir = tmp_path / "RPGGame"
        data_dir = project_dir / "www" / "data"
        data_dir.mkdir(parents=True)
        
        # Actors.json
        actors_data = [
            None,  # index 0 is null in RPG Maker
            {
                "id": 1,
                "name": "Hero",
                "nickname": "The Brave",
                "profile": "A young warrior",
                "classId": 1,
                "initialLevel": 1,
                "maxLevel": 99,
                "params": [[100, 200, 300], [50, 100, 150]],  # simplified
            },
            {
                "id": 2,
                "name": "Mage",
                "nickname": "The Wise",
                "profile": "A powerful wizard",
                "classId": 2,
                "initialLevel": 1,
                "maxLevel": 99,
                "params": [[80, 150, 250], [100, 200, 300]],
            },
        ]
        (data_dir / "Actors.json").write_text(json.dumps(actors_data))
        
        # Enemies.json
        enemies_data = [
            None,
            {
                "id": 1,
                "name": "Slime",
                "params": [30, 0, 5, 5, 5, 5, 5, 5],
                "exp": 10,
                "gold": 5,
                "dropItems": [{"dataId": 1, "denominator": 3, "kind": 1}],
                "actions": [{"conditionParam1": 0, "conditionParam2": 0, "conditionType": 0, "rating": 5, "skillId": 1}],
            },
        ]
        (data_dir / "Enemies.json").write_text(json.dumps(enemies_data))
        
        # Items.json
        items_data = [
            None,
            {
                "id": 1,
                "name": "Potion",
                "description": "Restores 50 HP",
                "itypeId": 1,
                "price": 50,
                "consumable": True,
                "effects": [{"code": 11, "dataId": 0, "value1": 0, "value2": 50}],
            },
        ]
        (data_dir / "Items.json").write_text(json.dumps(items_data))
        
        # Skills.json
        skills_data = [
            None,
            {
                "id": 1,
                "name": "Fire",
                "description": "Deals fire damage",
                "mpCost": 5,
                "tpCost": 0,
                "scope": 1,
                "damage": {"type": 1, "elementId": 2, "formula": "a.atk * 4 - b.def * 2"},
            },
        ]
        (data_dir / "Skills.json").write_text(json.dumps(skills_data))
        
        # System.json
        system_data = {
            "gameTitle": "Test RPG",
            "currencyUnit": "G",
            "battleSystem": 0,
            "menuCommands": [True, True, True, True, True, True, True, True],
        }
        (data_dir / "System.json").write_text(json.dumps(system_data))
        
        # Map001.json
        map_data = {
            "displayName": "Village",
            "width": 20,
            "height": 15,
            "events": [None, {"id": 1, "name": "NPC"}],
        }
        (data_dir / "Map001.json").write_text(json.dumps(map_data))
        
        return project_dir
    
    def test_analyze_rpgmv_actors(self, rpgmv_game_with_data: Path):
        """测试分析 RPG Maker 角色"""
        # 首先提取资源
        extractor = CompositeResourceExtractor()
        result = extractor.extract(rpgmv_game_with_data, GameEngine.RPG_MAKER)
        
        # 创建图谱
        graph = ContentGraph(
            source_path=str(rpgmv_game_with_data),
            media_type=MediaType.GAME,
        )
        graph.metadata.engine = GameEngine.RPG_MAKER
        for asset in result.assets:
            graph.add_asset(asset)
        
        # 分析机制
        analyzer = RPGMakerMechanismAnalyzer()
        analyzer.analyze(graph)
        
        # 检查角色
        characters = graph.get_nodes_by_type(NodeType.CHARACTER)
        assert len(characters) >= 2
        
        hero = [c for c in characters if c.name == "Hero"]
        assert len(hero) == 1
        assert hero[0].properties.get('character_type') == 'player'
        assert hero[0].properties['stats']['level'] == 1
    
    def test_analyze_rpgmv_system(self, rpgmv_game_with_data: Path):
        """测试分析系统配置"""
        extractor = CompositeResourceExtractor()
        result = extractor.extract(rpgmv_game_with_data, GameEngine.RPG_MAKER)
        
        graph = ContentGraph(
            source_path=str(rpgmv_game_with_data),
            media_type=MediaType.GAME,
        )
        graph.metadata.engine = GameEngine.RPG_MAKER
        for asset in result.assets:
            graph.add_asset(asset)
        
        analyzer = RPGMakerMechanismAnalyzer()
        analyzer.analyze(graph)
        
        # 检查标题
        assert graph.metadata.title == "Test RPG"
        
        # 检查机制节点
        mechanics = graph.get_nodes_by_type(NodeType.MECHANIC)
        assert len(mechanics) >= 2  # 经济系统 + 战斗系统


class TestPerceptionEngine:
    """完整感知引擎测试"""
    
    @pytest.fixture
    def unity_game_full(self, tmp_path: Path):
        """创建完整 Unity 游戏目录"""
        game_dir = tmp_path / "TestUnityGame"
        data_dir = game_dir / "TestUnityGame_Data"
        data_dir.mkdir(parents=True)
        
        # 引擎特征
        (data_dir / "globalgamemanagers").write_bytes(b"UnityFS\x05\x00\x00\x00" + b"\x00" * 100)
        
        # 资源
        textures_dir = data_dir / "Resources" / "Textures"
        textures_dir.mkdir(parents=True)
        
        png_file = textures_dir / "player.png"
        png_file.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x20"  # width: 32
            b"\x00\x00\x00\x20"  # height: 32
            b"\x08\x02\x00\x00\x00"
            b"\x90\x91h\x6b"
        )
        
        # 配置文件
        config_dir = data_dir / "StreamingAssets"
        config_dir.mkdir(parents=True)
        (config_dir / "game_config.json").write_text(json.dumps({
            "playerHealth": 100,
            "playerSpeed": 5.5,
            "enemyCount": 10,
            "difficulty": "normal",
        }))
        
        return game_dir
    
    @pytest.fixture
    def rpgmv_game_full(self, tmp_path: Path):
        """创建完整 RPG Maker MV 游戏目录"""
        project_dir = tmp_path / "TestRPG"
        www_dir = project_dir / "www"
        data_dir = www_dir / "data"
        data_dir.mkdir(parents=True)
        
        (www_dir / "index.html").write_text("<html></html>")
        js_dir = www_dir / "js"
        js_dir.mkdir(parents=True)
        (js_dir / "plugins.js").write_text("var $plugins = []")
        
        # System.json
        (data_dir / "System.json").write_text(json.dumps({
            "gameTitle": "Test RPG Game",
            "currencyUnit": "Gold",
            "battleSystem": 1,  # side_view
        }))
        
        # Actors.json
        (data_dir / "Actors.json").write_text(json.dumps([
            None,
            {"id": 1, "name": "Alice", "classId": 1, "initialLevel": 1, "maxLevel": 99, "params": [[100]]},
        ]))
        
        # Enemies.json
        (data_dir / "Enemies.json").write_text(json.dumps([
            None,
            {"id": 1, "name": "Goblin", "params": [50, 0, 8, 5], "exp": 15, "gold": 10},
        ]))
        
        return project_dir
    
    def test_perceive_unity_game(self, unity_game_full: Path):
        """测试感知 Unity 游戏"""
        engine = PerceptionEngine()
        graph = engine.perceive(unity_game_full)
        
        assert graph.media_type == MediaType.GAME
        assert graph.metadata.engine == GameEngine.UNITY
        assert graph.confidence > 0.3
        assert len(graph.assets) > 0
        
        # 检查资源
        textures = graph.get_assets_by_type('texture')
        assert len(textures) > 0
        
        # 检查语义
        assert graph.semantics.summary is not None
        assert "Unity" in graph.semantics.summary or "unity" in graph.semantics.summary
    
    def test_perceive_rpgmv_game(self, rpgmv_game_full: Path):
        """测试感知 RPG Maker MV 游戏"""
        engine = PerceptionEngine()
        graph = engine.perceive(rpgmv_game_full)
        
        assert graph.media_type == MediaType.GAME
        assert graph.metadata.engine == GameEngine.RPG_MAKER
        assert graph.confidence > 0.3
        assert len(graph.assets) > 0
        
        # 检查角色
        characters = graph.get_nodes_by_type(NodeType.CHARACTER)
        assert len(characters) >= 1
        
        # 检查标题
        assert graph.metadata.title == "Test RPG Game"
    
    def test_perceive_nonexistent_path(self, tmp_path: Path):
        """测试感知不存在的路径"""
        engine = PerceptionEngine()
        graph = engine.perceive(tmp_path / "nonexistent")
        
        assert graph.confidence == 0.0
        assert len(graph.assets) == 0


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_detect_engine_function(self, tmp_path: Path):
        """测试 detect_engine 便捷函数"""
        # 创建 Unity 游戏
        game_dir = tmp_path / "UnityGame"
        data_dir = game_dir / "UnityGame_Data"
        data_dir.mkdir(parents=True)
        (data_dir / "globalgamemanagers").write_bytes(b"UnityFS\x05\x00\x00\x00" + b"\x00" * 100)
        
        result = detect_engine(game_dir)
        assert result.engine == GameEngine.UNITY
    
    def test_extract_resources_function(self, tmp_path: Path):
        """测试 extract_resources 便捷函数"""
        # 创建带资源的 Unity 游戏目录
        game_dir = tmp_path / "Game"
        data_dir = game_dir / "Game_Data"
        data_dir.mkdir(parents=True)
        (data_dir / "globalgamemanagers").write_bytes(b"UnityFS\x05\x00\x00\x00" + b"\x00" * 100)
        
        textures_dir = data_dir / "Resources" / "Textures"
        textures_dir.mkdir(parents=True)
        (textures_dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        
        result = extract_resources(game_dir, GameEngine.UNITY)
        assert len(result.assets) > 0
        assert any(a.type == 'texture' for a in result.assets)


# 需要导入 struct 用于 Unreal 测试
import struct
