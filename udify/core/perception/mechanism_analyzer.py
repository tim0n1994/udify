"""
Udify Core - Mechanism Analyzer

机制分析器，从游戏的配置文件和脚本中提取游戏机制，
并生成结构化的机制描述节点。

这是感知引擎中最具挑战性的部分——它需要"理解"游戏的规则和系统。
"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from pathlib import Path

from udify.models.content_graph import (
    ContentAsset,
    ContentEdge,
    ContentGraph,
    ContentNode,
    EdgeType,
    GameEngine,
    NodeType,
)

logger = logging.getLogger(__name__)


class MechanismAnalyzer(ABC):
    """机制分析器基类"""

    @abstractmethod
    def analyze(self, graph: ContentGraph) -> None:
        """
        分析内容图谱中的机制

        Args:
            graph: 内容图谱（已包含资源和元数据）

        Note:
            分析结果直接修改传入的 graph，添加机制节点和边
        """
        pass

    @property
    @abstractmethod
    def supported_engine(self) -> GameEngine:
        """返回支持的引擎类型"""
        pass

    def _create_mechanic_node(self, name: str, description: str, **properties) -> ContentNode:
        """快速创建机制节点"""
        return ContentNode(
            type=NodeType.MECHANIC,
            name=name,
            properties={
                "description": description,
                **properties,
            },
        )

    def _create_level_node(self, name: str, **properties) -> ContentNode:
        """快速创建关卡节点"""
        return ContentNode(
            type=NodeType.LEVEL,
            name=name,
            properties=properties,
        )

    def _create_character_node(self, name: str, **properties) -> ContentNode:
        """快速创建角色节点"""
        return ContentNode(
            type=NodeType.CHARACTER,
            name=name,
            properties=properties,
        )

    def _create_event_node(self, name: str, **properties) -> ContentNode:
        """快速创建事件节点"""
        return ContentNode(
            type=NodeType.EVENT,
            name=name,
            properties=properties,
        )

    def _link_nodes(
        self,
        graph: ContentGraph,
        source_id: str,
        target_id: str,
        edge_type: EdgeType = EdgeType.DEPENDS_ON,
        weight: float = 1.0,
    ):
        """在图谱中创建边"""
        graph.add_edge(
            ContentEdge(
                source=source_id,
                target=target_id,
                type=edge_type,
                weight=weight,
            )
        )


class UnityMechanismAnalyzer(MechanismAnalyzer):
    """Unity 游戏机制分析器"""

    @property
    def supported_engine(self) -> GameEngine:
        return GameEngine.UNITY

    def analyze(self, graph: ContentGraph) -> None:
        logger.info("Analyzing Unity game mechanisms...")

        # 1. 分析场景文件
        self._analyze_scenes(graph)

        # 2. 分析脚本文件
        self._analyze_scripts(graph)

        # 3. 分析配置文件
        self._analyze_configs(graph)

        # 4. 分析资源依赖关系
        self._analyze_resource_dependencies(graph)

    def _analyze_scenes(self, graph: ContentGraph) -> None:
        """分析场景文件"""
        scene_assets = [
            a
            for a in graph.assets
            if a.type in ("scene", "unity_asset") and "scene" in a.path.lower()
        ]

        for asset in scene_assets:
            # 创建关卡节点
            scene_name = Path(asset.path).stem
            level_node = self._create_level_node(
                name=scene_name,
                source_file=asset.path,
            )
            graph.add_node(level_node)

            # 关联资源
            # 简化：假设同目录下的资源属于该场景
            scene_dir = Path(asset.path).parent
            related_assets = [a for a in graph.assets if Path(a.path).parent == scene_dir]

            for related in related_assets:
                if related.type in ("texture", "model", "audio"):
                    self._link_nodes(graph, level_node.id, related.id, EdgeType.CONTAINS)

    def _analyze_scripts(self, graph: ContentGraph) -> None:
        """分析脚本文件，提取机制信息"""
        script_assets = [a for a in graph.assets if a.type == "script"]

        for asset in script_assets:
            # 这里可以集成 LLM 来理解脚本内容
            # 目前使用基于关键词的启发式方法
            self._analyze_script_keywords(graph, asset)

    def _analyze_script_keywords(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """基于关键词分析脚本"""
        # 常见 Unity 脚本中的机制关键词
        mechanic_keywords = {
            "health": ("生命值系统", "health_system"),
            "damage": ("伤害系统", "damage_system"),
            "exp": ("经验值系统", "experience_system"),
            "levelup": ("升级系统", "leveling_system"),
            "inventory": ("背包系统", "inventory_system"),
            "quest": ("任务系统", "quest_system"),
            "dialogue": ("对话系统", "dialogue_system"),
            "combat": ("战斗系统", "combat_system"),
            "crafting": ("制作系统", "crafting_system"),
            "skill": ("技能系统", "skill_system"),
            "ai": ("AI 系统", "ai_system"),
            "pathfinding": ("寻路系统", "pathfinding_system"),
            "physics": ("物理系统", "physics_system"),
            "animation": ("动画系统", "animation_system"),
            "save": ("存档系统", "save_system"),
            "ui": ("UI 系统", "ui_system"),
            "input": ("输入系统", "input_system"),
            "camera": ("摄像机系统", "camera_system"),
            "audio": ("音频系统", "audio_system"),
            "particle": ("粒子系统", "particle_system"),
            "lighting": ("光照系统", "lighting_system"),
        }

        try:
            # 尝试读取脚本内容
            # 注意：这里假设脚本在源码项目中
            # 对于编译后的游戏，需要反编译（如使用 ILSpy 等工具）
            script_path = Path(graph.source_path) / asset.path
            if script_path.exists():
                content = script_path.read_text(encoding="utf-8", errors="ignore").lower()

                for keyword, (cn_name, en_name) in mechanic_keywords.items():
                    if keyword in content:
                        # 检查是否已存在相同机制
                        existing = [
                            n
                            for n in graph.nodes
                            if n.type == NodeType.MECHANIC and n.name == cn_name
                        ]

                        if not existing:
                            mechanic_node = self._create_mechanic_node(
                                name=cn_name,
                                description=f"Detected {en_name} in {asset.path}",
                                source_file=asset.path,
                                detected_by="keyword",
                            )
                            graph.add_node(mechanic_node)

                            # 关联到脚本资源
                            resource_nodes = [n for n in graph.nodes if n.source_path == asset.path]
                            if resource_nodes:
                                self._link_nodes(
                                    graph,
                                    mechanic_node.id,
                                    resource_nodes[0].id,
                                    EdgeType.REFERENCES,
                                )
        except Exception as e:
            logger.debug(f"Failed to analyze script {asset.path}: {e}")

    def _analyze_configs(self, graph: ContentGraph) -> None:
        """分析配置文件"""
        config_assets = [a for a in graph.assets if a.type == "config"]

        for asset in config_assets:
            try:
                config_path = Path(graph.source_path) / asset.path
                if not config_path.exists():
                    continue

                # 根据文件类型解析
                if asset.format == "json":
                    self._analyze_json_config(graph, asset, config_path)
                elif asset.format == "xml":
                    self._analyze_xml_config(graph, asset, config_path)
                elif asset.format in ("yaml", "yml"):
                    self._analyze_yaml_config(graph, asset, config_path)

            except Exception as e:
                logger.debug(f"Failed to analyze config {asset.path}: {e}")

    def _analyze_json_config(
        self, graph: ContentGraph, asset: ContentAsset, config_path: Path
    ) -> None:
        """分析 JSON 配置文件"""
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)

            # 根据文件名判断配置类型
            filename = config_path.stem.lower()

            if any(x in filename for x in ["player", "character", "hero"]):
                self._extract_player_config(graph, asset, data)
            elif any(x in filename for x in ["enemy", "monster", "npc"]):
                self._extract_character_config(graph, asset, data, "enemy")
            elif any(x in filename for x in ["item", "equipment", "weapon"]):
                self._extract_item_config(graph, asset, data)
            elif any(x in filename for x in ["level", "stage", "map"]):
                self._extract_level_config(graph, asset, data)
            elif any(x in filename for x in ["quest", "mission", "task"]):
                self._extract_quest_config(graph, asset, data)
            elif any(x in filename for x in ["skill", "ability", "spell"]):
                self._extract_skill_config(graph, asset, data)
            else:
                # 通用配置分析
                self._extract_generic_config(graph, asset, data)

        except Exception as e:
            logger.debug(f"Failed to parse JSON config {asset.path}: {e}")

    def _extract_player_config(self, graph: ContentGraph, asset: ContentAsset, data: dict) -> None:
        """提取玩家配置"""
        # 创建玩家角色节点
        player_node = self._create_character_node(
            name="Player",
            character_type="player",
            source_file=asset.path,
        )

        # 提取属性
        if isinstance(data, dict):
            stats = {}
            for key in ["health", "hp", "maxHealth", "maxHp", "life"]:
                if key in data:
                    stats["health"] = data[key]
                    break
            for key in ["speed", "moveSpeed", "walkSpeed"]:
                if key in data:
                    stats["speed"] = data[key]
                    break
            for key in ["damage", "attack", "attackPower", "strength"]:
                if key in data:
                    stats["attack"] = data[key]
                    break

            if stats:
                player_node.properties["stats"] = stats

        graph.add_node(player_node)

        # 关联到机制
        health_nodes = [n for n in graph.nodes if n.type == NodeType.MECHANIC and "生命" in n.name]
        if health_nodes:
            self._link_nodes(graph, player_node.id, health_nodes[0].id, EdgeType.DEPENDS_ON)

    def _extract_character_config(
        self, graph: ContentGraph, asset: ContentAsset, data: dict, char_type: str
    ) -> None:
        """提取角色配置"""
        if isinstance(data, dict):
            # 可能是单个角色
            name = data.get("name", data.get("id", Path(asset.path).stem))
            char_node = self._create_character_node(
                name=str(name),
                character_type=char_type,
                source_file=asset.path,
            )

            # 提取属性
            if "stats" in data:
                char_node.properties["stats"] = data["stats"]
            if "level" in data:
                char_node.properties["level"] = data["level"]

            graph.add_node(char_node)

        elif isinstance(data, list):
            # 角色列表
            for char_data in data:
                if isinstance(char_data, dict):
                    name = char_data.get("name", char_data.get("id", "Unknown"))
                    char_node = self._create_character_node(
                        name=str(name),
                        character_type=char_type,
                        source_file=asset.path,
                    )

                    if "stats" in char_data:
                        char_node.properties["stats"] = char_data["stats"]

                    graph.add_node(char_node)

    def _extract_item_config(self, graph: ContentGraph, asset: ContentAsset, data: dict) -> None:
        """提取物品配置"""
        if isinstance(data, list):
            for item_data in data:
                if isinstance(item_data, dict):
                    name = item_data.get("name", item_data.get("id", "Unknown"))
                    item_node = ContentNode(
                        type=NodeType.ITEM,
                        name=str(name),
                        properties={
                            "item_type": item_data.get("type", "unknown"),
                            "rarity": item_data.get("rarity", "common"),
                            "source_file": asset.path,
                        },
                    )
                    graph.add_node(item_node)

    def _extract_level_config(self, graph: ContentGraph, asset: ContentAsset, data: dict) -> None:
        """提取关卡配置"""
        if isinstance(data, dict):
            level_name = data.get("name", data.get("id", Path(asset.path).stem))
            level_node = self._create_level_node(
                name=str(level_name),
                source_file=asset.path,
            )

            if "difficulty" in data:
                level_node.properties["difficulty"] = data["difficulty"]
            if "enemies" in data:
                level_node.properties["enemy_count"] = len(data["enemies"])
            if "rewards" in data:
                level_node.properties["rewards"] = data["rewards"]

            graph.add_node(level_node)

    def _extract_quest_config(self, graph: ContentGraph, asset: ContentAsset, data: dict) -> None:
        """提取任务配置"""
        if isinstance(data, list):
            for quest_data in data:
                if isinstance(quest_data, dict):
                    name = quest_data.get("name", quest_data.get("id", "Unknown"))
                    quest_node = ContentNode(
                        type=NodeType.QUEST,
                        name=str(name),
                        properties={
                            "description": quest_data.get("description", ""),
                            "objectives": quest_data.get("objectives", []),
                            "rewards": quest_data.get("rewards", []),
                            "source_file": asset.path,
                        },
                    )
                    graph.add_node(quest_node)

    def _extract_skill_config(self, graph: ContentGraph, asset: ContentAsset, data: dict) -> None:
        """提取技能配置"""
        if isinstance(data, list):
            for skill_data in data:
                if isinstance(skill_data, dict):
                    name = skill_data.get("name", skill_data.get("id", "Unknown"))
                    # 创建事件节点表示技能
                    skill_node = self._create_event_node(
                        name=str(name),
                        event_type="skill",
                        source_file=asset.path,
                    )

                    if "damage" in skill_data:
                        skill_node.properties["damage"] = skill_data["damage"]
                    if "cooldown" in skill_data:
                        skill_node.properties["cooldown"] = skill_data["cooldown"]
                    if "mana_cost" in skill_data:
                        skill_node.properties["mana_cost"] = skill_data["mana_cost"]

                    graph.add_node(skill_node)

    def _extract_generic_config(self, graph: ContentGraph, asset: ContentAsset, data: dict) -> None:
        """通用配置分析"""
        # 尝试识别数值配置（如平衡参数）
        if isinstance(data, dict):
            numeric_values = {k: v for k, v in data.items() if isinstance(v, (int, float))}

            if len(numeric_values) > 3:  # 如果有多个数值，可能是平衡配置
                config_node = self._create_mechanic_node(
                    name=f"Config: {Path(asset.path).stem}",
                    description=f"Balance configuration with {len(numeric_values)} parameters",
                    source_file=asset.path,
                    parameters=numeric_values,
                )
                graph.add_node(config_node)

    def _analyze_xml_config(
        self, graph: ContentGraph, asset: ContentAsset, config_path: Path
    ) -> None:
        """分析 XML 配置文件"""
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()

            # 根据根元素判断类型
            tag = root.tag.lower()

            if any(x in tag for x in ["player", "character"]):
                self._extract_xml_characters(graph, asset, root)
            elif any(x in tag for x in ["item", "equipment"]):
                self._extract_xml_items(graph, asset, root)
            elif any(x in tag for x in ["level", "stage"]):
                self._extract_xml_levels(graph, asset, root)

        except Exception as e:
            logger.debug(f"Failed to parse XML config {asset.path}: {e}")

    def _extract_xml_characters(
        self, graph: ContentGraph, asset: ContentAsset, root: ET.Element
    ) -> None:
        """从 XML 提取角色信息"""
        for char_elem in (
            root.findall(".//character") + root.findall(".//player") + root.findall(".//enemy")
        ):
            name = char_elem.get("name", char_elem.get("id", "Unknown"))
            char_type = "enemy" if char_elem.tag == "enemy" else "player"

            char_node = self._create_character_node(
                name=name,
                character_type=char_type,
                source_file=asset.path,
            )

            # 提取属性
            stats = {}
            for stat_elem in char_elem:
                if stat_elem.text and stat_elem.text.strip().replace(".", "").isdigit():
                    stats[stat_elem.tag] = float(stat_elem.text)

            if stats:
                char_node.properties["stats"] = stats

            graph.add_node(char_node)

    def _extract_xml_items(
        self, graph: ContentGraph, asset: ContentAsset, root: ET.Element
    ) -> None:
        """从 XML 提取物品信息"""
        for item_elem in root.findall(".//item") + root.findall(".//equipment"):
            name = item_elem.get("name", item_elem.get("id", "Unknown"))

            item_node = ContentNode(
                type=NodeType.ITEM,
                name=name,
                properties={
                    "item_type": item_elem.get("type", "unknown"),
                    "source_file": asset.path,
                },
            )

            graph.add_node(item_node)

    def _extract_xml_levels(
        self, graph: ContentGraph, asset: ContentAsset, root: ET.Element
    ) -> None:
        """从 XML 提取关卡信息"""
        for level_elem in (
            root.findall(".//level") + root.findall(".//stage") + root.findall(".//map")
        ):
            name = level_elem.get("name", level_elem.get("id", "Unknown"))

            level_node = self._create_level_node(
                name=name,
                source_file=asset.path,
            )

            if "difficulty" in level_elem.attrib:
                level_node.properties["difficulty"] = level_elem.get("difficulty")

            graph.add_node(level_node)

    def _analyze_yaml_config(
        self, graph: ContentGraph, asset: ContentAsset, config_path: Path
    ) -> None:
        """分析 YAML 配置文件"""
        # YAML 解析可以复用 JSON 解析的逻辑结构
        try:
            import yaml

            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if isinstance(data, dict):
                self._extract_generic_config(graph, asset, data)
        except ImportError:
            logger.debug("PyYAML not installed, skipping YAML analysis")
        except Exception as e:
            logger.debug(f"Failed to parse YAML config {asset.path}: {e}")

    def _analyze_resource_dependencies(self, graph: ContentGraph) -> None:
        """分析资源之间的依赖关系"""
        # 简化实现：基于路径关系推断依赖
        for asset in graph.assets:
            asset_dir = Path(asset.path).parent

            # 查找同目录下的其他资源
            related = [
                a for a in graph.assets if Path(a.path).parent == asset_dir and a.path != asset.path
            ]

            for rel in related:
                # 创建资源节点（如果不存在）
                asset_nodes = [n for n in graph.nodes if n.source_path == asset.path]
                rel_nodes = [n for n in graph.nodes if n.source_path == rel.path]

                if asset_nodes and rel_nodes:
                    self._link_nodes(graph, asset_nodes[0].id, rel_nodes[0].id, EdgeType.RELATED_TO)


class RPGMakerMechanismAnalyzer(MechanismAnalyzer):
    """RPG Maker 机制分析器"""

    @property
    def supported_engine(self) -> GameEngine:
        return GameEngine.RPG_MAKER

    def analyze(self, graph: ContentGraph) -> None:
        logger.info("Analyzing RPG Maker game mechanisms...")

        # 1. 分析数据文件（JSON 或二进制）
        self._analyze_data_files(graph)

        # 2. 分析地图文件
        self._analyze_maps(graph)

        # 3. 分析系统配置
        self._analyze_system_config(graph)

    def _analyze_data_files(self, graph: ContentGraph) -> None:
        """分析 RPG Maker 数据文件"""
        # MV/MZ 使用 JSON 文件
        json_assets = [a for a in graph.assets if a.format == "json"]

        for asset in json_assets:
            filename = Path(asset.path).stem.lower()

            if "actors" in filename:
                self._extract_rpgmv_actors(graph, asset)
            elif "enemies" in filename:
                self._extract_rpgmv_enemies(graph, asset)
            elif "items" in filename:
                self._extract_rpgmv_items(graph, asset)
            elif "skills" in filename:
                self._extract_rpgmv_skills(graph, asset)
            elif "classes" in filename:
                self._extract_rpgmv_classes(graph, asset)
            elif "weapons" in filename:
                self._extract_rpgmv_weapons(graph, asset)
            elif "armors" in filename:
                self._extract_rpgmv_armors(graph, asset)
            elif "troops" in filename:
                self._extract_rpgmv_troops(graph, asset)
            elif "states" in filename:
                self._extract_rpgmv_states(graph, asset)

    def _extract_rpgmv_actors(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取 RPG Maker MV/MZ 角色"""
        try:
            data_path = Path(graph.source_path) / asset.path
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                for actor_data in data:
                    if not actor_data:
                        continue

                    name = actor_data.get("name", "Unknown")
                    if not name or name == "":
                        continue

                    char_node = self._create_character_node(
                        name=name,
                        character_type="player",
                        source_file=asset.path,
                    )

                    # RPG Maker 标准属性
                    stats = {
                        "level": actor_data.get("initialLevel", 1),
                        "max_level": actor_data.get("maxLevel", 99),
                    }

                    # 参数曲线
                    if "params" in actor_data:
                        stats["param_curves"] = actor_data["params"]

                    char_node.properties["stats"] = stats
                    char_node.properties["nickname"] = actor_data.get("nickname", "")
                    char_node.properties["profile"] = actor_data.get("profile", "")
                    char_node.properties["class_id"] = actor_data.get("classId", 0)

                    graph.add_node(char_node)

        except Exception as e:
            logger.debug(f"Failed to extract actors from {asset.path}: {e}")

    def _extract_rpgmv_enemies(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取敌人"""
        try:
            data_path = Path(graph.source_path) / asset.path
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                for enemy_data in data:
                    if not enemy_data:
                        continue

                    name = enemy_data.get("name", "Unknown")
                    if not name:
                        continue

                    char_node = self._create_character_node(
                        name=name,
                        character_type="enemy",
                        source_file=asset.path,
                    )

                    stats = {
                        "hp": enemy_data.get("params", [0])[0] if "params" in enemy_data else 0,
                        "mp": enemy_data.get("params", [0, 0])[1]
                        if "params" in enemy_data and len(enemy_data["params"]) > 1
                        else 0,
                        "attack": enemy_data.get("params", [0, 0, 0])[2]
                        if "params" in enemy_data and len(enemy_data["params"]) > 2
                        else 0,
                        "defense": enemy_data.get("params", [0, 0, 0, 0])[3]
                        if "params" in enemy_data and len(enemy_data["params"]) > 3
                        else 0,
                    }

                    char_node.properties["stats"] = stats
                    char_node.properties["exp"] = enemy_data.get("exp", 0)
                    char_node.properties["gold"] = enemy_data.get("gold", 0)

                    # 掉落物品
                    if "dropItems" in enemy_data:
                        char_node.properties["drop_items"] = enemy_data["dropItems"]

                    # 行动模式（AI）
                    if "actions" in enemy_data:
                        char_node.properties["ai_actions"] = enemy_data["actions"]

                    graph.add_node(char_node)

        except Exception as e:
            logger.debug(f"Failed to extract enemies from {asset.path}: {e}")

    def _extract_rpgmv_items(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取物品"""
        try:
            data_path = Path(graph.source_path) / asset.path
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                for item_data in data:
                    if not item_data:
                        continue

                    name = item_data.get("name", "Unknown")
                    if not name:
                        continue

                    item_node = ContentNode(
                        type=NodeType.ITEM,
                        name=name,
                        properties={
                            "item_type": self._get_rpgmv_item_type(item_data.get("itypeId", 1)),
                            "description": item_data.get("description", ""),
                            "price": item_data.get("price", 0),
                            "consumable": item_data.get("consumable", True),
                            "source_file": asset.path,
                        },
                    )

                    # 效果
                    if "effects" in item_data:
                        item_node.properties["effects"] = item_data["effects"]

                    graph.add_node(item_node)

        except Exception as e:
            logger.debug(f"Failed to extract items from {asset.path}: {e}")

    def _get_rpgmv_item_type(self, itype_id: int) -> str:
        """获取 RPG Maker 物品类型"""
        types = {1: "regular_item", 2: "key_item"}
        return types.get(itype_id, "unknown")

    def _extract_rpgmv_skills(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取技能"""
        try:
            data_path = Path(graph.source_path) / asset.path
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                for skill_data in data:
                    if not skill_data:
                        continue

                    name = skill_data.get("name", "Unknown")
                    if not name:
                        continue

                    skill_node = self._create_event_node(
                        name=name,
                        event_type="skill",
                        source_file=asset.path,
                    )

                    skill_node.properties["description"] = skill_data.get("description", "")
                    skill_node.properties["mp_cost"] = skill_data.get("mpCost", 0)
                    skill_node.properties["tp_cost"] = skill_data.get("tpCost", 0)
                    skill_node.properties["scope"] = skill_data.get("scope", 0)
                    skill_node.properties["damage"] = skill_data.get("damage", {})

                    graph.add_node(skill_node)

        except Exception as e:
            logger.debug(f"Failed to extract skills from {asset.path}: {e}")

    def _extract_rpgmv_classes(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取职业"""
        # 职业定义了角色的成长曲线和可装备类型
        pass  # 简化实现

    def _extract_rpgmv_weapons(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取武器"""
        # 复用物品提取逻辑
        self._extract_rpgmv_items(graph, asset)

    def _extract_rpgmv_armors(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取防具"""
        # 复用物品提取逻辑
        self._extract_rpgmv_items(graph, asset)

    def _extract_rpgmv_troops(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取 troop（敌人编队）"""
        try:
            data_path = Path(graph.source_path) / asset.path
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                for troop_data in data:
                    if not troop_data:
                        continue

                    name = troop_data.get("name", "Unknown")
                    if not name:
                        continue

                    # Troop 是敌人组合，创建为关卡/遭遇节点
                    encounter_node = self._create_level_node(
                        name=f"Encounter: {name}",
                        source_file=asset.path,
                    )

                    if "members" in troop_data:
                        encounter_node.properties["enemy_count"] = len(troop_data["members"])
                        encounter_node.properties["enemies"] = troop_data["members"]

                    graph.add_node(encounter_node)

        except Exception as e:
            logger.debug(f"Failed to extract troops from {asset.path}: {e}")

    def _extract_rpgmv_states(self, graph: ContentGraph, asset: ContentAsset) -> None:
        """提取状态"""
        # 状态是 RPG Maker 中的 buff/debuff 机制
        pass  # 简化实现

    def _analyze_maps(self, graph: ContentGraph) -> None:
        """分析地图文件"""
        # MV/MZ: data/MapXXX.json
        map_assets = [a for a in graph.assets if a.format == "json" and "map" in a.path.lower()]

        for asset in map_assets:
            try:
                data_path = Path(graph.source_path) / asset.path
                with open(data_path, encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict):
                    map_name = data.get("displayName", Path(asset.path).stem)

                    level_node = self._create_level_node(
                        name=map_name,
                        source_file=asset.path,
                    )

                    if "width" in data and "height" in data:
                        level_node.properties["size"] = f"{data['width']}x{data['height']}"

                    if "events" in data:
                        events = data["events"]
                        level_node.properties["event_count"] = len([e for e in events if e])

                    graph.add_node(level_node)

            except Exception as e:
                logger.debug(f"Failed to analyze map {asset.path}: {e}")

    def _analyze_system_config(self, graph: ContentGraph) -> None:
        """分析系统配置"""
        system_assets = [
            a for a in graph.assets if "system" in a.path.lower() and a.format == "json"
        ]

        for asset in system_assets:
            try:
                data_path = Path(graph.source_path) / asset.path
                with open(data_path, encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict):
                    # 提取游戏标题
                    if "gameTitle" in data:
                        graph.metadata.title = data["gameTitle"]

                    # 提取货币单位
                    if "currencyUnit" in data:
                        currency_node = self._create_mechanic_node(
                            name="经济系统",
                            description=f"货币单位: {data['currencyUnit']}",
                            source_file=asset.path,
                            currency_unit=data["currencyUnit"],
                        )
                        graph.add_node(currency_node)

                    # 提取战斗系统类型
                    if "battleSystem" in data:
                        battle_type = {0: "front_view", 1: "side_view"}.get(
                            data["battleSystem"], "unknown"
                        )
                        battle_node = self._create_mechanic_node(
                            name="战斗系统",
                            description=f"战斗视角: {battle_type}",
                            source_file=asset.path,
                            battle_type=battle_type,
                        )
                        graph.add_node(battle_node)

                    # 提取菜单命令
                    if "menuCommands" in data:
                        graph.semantics.features = data["menuCommands"]

            except Exception as e:
                logger.debug(f"Failed to analyze system config {asset.path}: {e}")


class CompositeMechanismAnalyzer:
    """组合机制分析器"""

    def __init__(self):
        self.analyzers: dict[GameEngine, MechanismAnalyzer] = {
            GameEngine.UNITY: UnityMechanismAnalyzer(),
            GameEngine.RPG_MAKER: RPGMakerMechanismAnalyzer(),
        }

    def analyze(self, graph: ContentGraph) -> None:
        """
        根据引擎类型分析机制

        Args:
            graph: 内容图谱
        """
        analyzer = self.analyzers.get(graph.metadata.engine)

        if analyzer:
            logger.info(f"Analyzing mechanisms using {analyzer.__class__.__name__}")
            analyzer.analyze(graph)
        else:
            logger.warning(f"No mechanism analyzer for engine: {graph.metadata.engine.value}")
            # 使用通用分析器作为后备
            self._generic_analysis(graph)

    def _generic_analysis(self, graph: ContentGraph) -> None:
        """通用机制分析（适用于未知引擎）"""
        logger.info("Running generic mechanism analysis...")

        # 1. 分析所有配置文件中的数值模式
        config_assets = [a for a in graph.assets if a.type == "config"]

        for asset in config_assets:
            try:
                config_path = Path(graph.source_path) / asset.path
                if not config_path.exists():
                    continue

                # 尝试解析为 JSON
                if asset.format == "json":
                    with open(config_path, encoding="utf-8") as f:
                        data = json.load(f)

                    if isinstance(data, dict):
                        # 查找数值模式（可能是平衡参数）
                        numeric_values = {
                            k: v for k, v in data.items() if isinstance(v, (int, float))
                        }

                        if len(numeric_values) > 5:
                            # 可能是游戏平衡配置
                            mechanic_node = ContentNode(
                                type=NodeType.MECHANIC,
                                name=f"Balance: {Path(asset.path).stem}",
                                properties={
                                    "description": f"Configuration with {len(numeric_values)} numeric parameters",
                                    "parameters": list(numeric_values.keys())[:10],  # 前 10 个参数
                                    "source_file": asset.path,
                                },
                            )
                            graph.add_node(mechanic_node)

            except Exception as e:
                logger.debug(f"Generic analysis failed for {asset.path}: {e}")

        # 2. 基于资源类型推断机制
        self._infer_mechanics_from_resources(graph)

    def _infer_mechanics_from_resources(self, graph: ContentGraph) -> None:
        """基于资源类型推断游戏机制"""
        resource_types = {}
        for asset in graph.assets:
            resource_types[asset.type] = resource_types.get(asset.type, 0) + 1

        # 根据资源分布推断游戏类型和机制
        if resource_types.get("texture", 0) > 50:
            # 大量纹理 = 可能是 2D 游戏或详细 3D 游戏
            pass

        if resource_types.get("model", 0) > 20:
            # 大量模型 = 3D 游戏
            mechanic = ContentNode(
                type=NodeType.MECHANIC,
                name="3D 渲染",
                properties={"inferred_from": "model_count", "model_count": resource_types["model"]},
            )
            graph.add_node(mechanic)

        if resource_types.get("audio", 0) > 10:
            # 大量音频 = 可能有复杂音效系统
            mechanic = ContentNode(
                type=NodeType.MECHANIC,
                name="音频系统",
                properties={"inferred_from": "audio_count", "audio_count": resource_types["audio"]},
            )
            graph.add_node(mechanic)


# 便捷函数
def analyze_mechanisms(graph: ContentGraph) -> None:
    """
    便捷函数：分析游戏机制

    Example:
        >>> analyze_mechanisms(graph)
        >>> print(f"Found {len(graph.get_nodes_by_type(NodeType.MECHANIC))} mechanisms")
    """
    analyzer = CompositeMechanismAnalyzer()
    analyzer.analyze(graph)
