"""
Udify Core - Content Description Language (CDL) Models

内容描述语言的数据模型，作为感知引擎的输出和整个系统的中间表示。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import numpy as np

if TYPE_CHECKING:
    from udify.models.source import Confidence, Provenance, SourceSpan


class MediaType(Enum):
    """媒介类型"""

    GAME = "game"
    MUSIC = "music"
    VIDEO = "video"
    NOVEL = "novel"
    UNKNOWN = "unknown"


class GameEngine(Enum):
    """游戏引擎类型"""

    UNITY = "unity"
    UNREAL = "unreal"
    GODOT = "godot"
    RPG_MAKER = "rpg_maker"
    GAME_MAKER = "game_maker"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class NodeType(Enum):
    """内容图谱节点类型"""

    # 通用
    RESOURCE = auto()
    CONTAINER = auto()

    # 游戏特有
    MECHANIC = auto()
    LEVEL = auto()
    CHARACTER = auto()
    ITEM = auto()
    EVENT = auto()
    DIALOGUE = auto()
    QUEST = auto()

    # 音乐特有
    TRACK = auto()
    CHORD_PROGRESSION = auto()
    MELODY = auto()
    RHYTHM = auto()
    INSTRUMENT = auto()

    # 视频特有
    SCENE = auto()
    SHOT = auto()
    TRANSITION = auto()

    # 小说特有
    CHAPTER = auto()
    PLOT_POINT = auto()
    SETTING = auto()
    THEME = auto()


class EdgeType(Enum):
    """内容图谱边类型"""

    DEPENDS_ON = "depends_on"
    CONTAINS = "contains"
    REFERENCES = "references"
    TRIGGERS = "triggers"
    REQUIRES = "requires"
    EXCLUDES = "excludes"
    SIMILAR_TO = "similar_to"
    PRECEDES = "precedes"
    FOLLOWS = "follows"


@dataclass
class ContentMetadata:
    """内容元数据"""

    title: str | None = None
    description: str | None = None
    version: str | None = None
    author: str | None = None
    creation_date: datetime | None = None
    tags: list[str] = field(default_factory=list)
    source: str = "unknown"  # original, derivative, mod

    # 游戏特有
    engine: GameEngine = GameEngine.UNKNOWN
    engine_version: str | None = None
    platform: list[str] = field(default_factory=list)  # pc, android, ios, etc.

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "creation_date": self.creation_date.isoformat() if self.creation_date else None,
            "tags": self.tags,
            "source": self.source,
            "engine": self.engine.value if self.engine else None,
            "engine_version": self.engine_version,
            "platform": self.platform,
        }


@dataclass
class ContentNode:
    """内容图谱节点"""

    id: str = field(default_factory=lambda: str(uuid4()))
    type: NodeType = NodeType.RESOURCE
    name: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    embedding: np.ndarray | None = None
    media_type: MediaType = MediaType.UNKNOWN

    # 源文件追踪
    source_path: str | None = None
    source_offset: int | None = None

    # v3 证据链（optional，向后兼容；DATA-CG-01..05）
    semantic_tags: list[str] = field(default_factory=list)
    provenance: Provenance | None = None
    confidence: Confidence | None = None
    license_hint: str = "unknown"  # unknown / proprietary / open / cc-by / ...
    source_span: SourceSpan | None = None

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ContentNode):
            return NotImplemented
        return self.id == other.id

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "type": self.type.name,
            "name": self.name,
            "properties": self.properties,
            "media_type": self.media_type.value,
            "source_path": self.source_path,
            "source_offset": self.source_offset,
        }
        if self.embedding is not None:
            result["embedding"] = self.embedding.tolist()
        # v3 证据链（仅在有值时输出，保持旧格式向后兼容）
        if self.semantic_tags:
            result["semantic_tags"] = self.semantic_tags
        if self.provenance is not None and hasattr(self.provenance, "to_dict"):
            result["provenance"] = self.provenance.to_dict()
        if self.confidence is not None and hasattr(self.confidence, "to_dict"):
            result["confidence"] = self.confidence.to_dict()
        if self.license_hint != "unknown":
            result["license_hint"] = self.license_hint
        return result


@dataclass
class ContentEdge:
    """内容图谱边"""

    source: str  # 节点 ID
    target: str  # 节点 ID
    type: EdgeType = EdgeType.DEPENDS_ON
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type.value,
            "weight": self.weight,
            "properties": self.properties,
        }


@dataclass
class ContentAsset:
    """内容资源（原始文件）"""

    id: str = field(default_factory=lambda: str(uuid4()))
    path: str = ""  # 文件路径（相对路径）
    type: str = ""  # texture, model, audio, script, text, config, etc.
    format: str = ""  # png, fbx, wav, cs, json, etc.
    size: int = 0  # 字节
    hash: str | None = None  # SHA-256

    # 解析后的元数据
    width: int | None = None  # 图像/视频
    height: int | None = None
    duration: float | None = None  # 音频/视频（秒）
    sample_rate: int | None = None  # 音频

    # v3 证据链（optional，向后兼容；DATA-CG-01..05）
    provenance: Provenance | None = None
    confidence: Confidence | None = None
    license_hint: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "type": self.type,
            "format": self.format,
            "size": self.size,
            "hash": self.hash,
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "sample_rate": self.sample_rate,
            "license_hint": self.license_hint,
        }


@dataclass
class ContentSemantics:
    """内容语义信息"""

    themes: list[str] = field(default_factory=list)
    mood: str | None = None
    genre: str | None = None
    style_description: str | None = None
    summary: str | None = None

    # 游戏特有
    game_genre: str | None = None  # rpg, fps, platformer, etc.
    perspective: str | None = None  # first_person, third_person, top_down, etc.
    pacing: str | None = None  # slow, moderate, fast
    difficulty: str | None = None  # easy, normal, hard, souls_like

    def to_dict(self) -> dict[str, Any]:
        return {
            "themes": self.themes,
            "mood": self.mood,
            "genre": self.genre,
            "style_description": self.style_description,
            "summary": self.summary,
            "game_genre": self.game_genre,
            "perspective": self.perspective,
            "pacing": self.pacing,
            "difficulty": self.difficulty,
        }


@dataclass
class ContentGraph:
    """
    内容图谱 - 感知引擎的核心输出

    将原始内容解析为图结构，包含节点、边、资源、语义信息。
    这是整个 Udify 系统的中间表示层。
    """

    id: UUID = field(default_factory=uuid4)
    media_type: MediaType = MediaType.UNKNOWN
    metadata: ContentMetadata = field(default_factory=ContentMetadata)
    nodes: list[ContentNode] = field(default_factory=list)
    edges: list[ContentEdge] = field(default_factory=list)
    assets: list[ContentAsset] = field(default_factory=list)
    semantics: ContentSemantics = field(default_factory=ContentSemantics)

    # 原始内容路径
    source_path: str | None = None

    # 解析时间戳
    parsed_at: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))

    # 解析置信度 (0.0 - 1.0)
    confidence: float = 0.0

    def add_node(self, node: ContentNode) -> ContentNode:
        """添加节点，如果已存在则返回现有节点"""
        for existing in self.nodes:
            if existing.id == node.id:
                return existing
        self.nodes.append(node)
        return node

    def add_edge(self, edge: ContentEdge) -> ContentEdge:
        """添加边，避免重复"""
        for existing in self.edges:
            if (
                existing.source == edge.source
                and existing.target == edge.target
                and existing.type == edge.type
            ):
                return existing
        self.edges.append(edge)
        return edge

    def add_asset(self, asset: ContentAsset) -> None:
        """添加资源"""
        self.assets.append(asset)

    def get_node(self, node_id: str) -> ContentNode | None:
        """通过 ID 获取节点"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_neighbors(
        self, node_id: str, edge_type: EdgeType | None = None
    ) -> list[tuple[ContentNode, ContentEdge]]:
        """获取节点的邻居"""
        results = []
        for edge in self.edges:
            if edge.source == node_id and (edge_type is None or edge.type == edge_type):
                target = self.get_node(edge.target)
                if target:
                    results.append((target, edge))
        return results

    def get_nodes_by_type(self, node_type: NodeType) -> list[ContentNode]:
        """获取特定类型的所有节点"""
        return [n for n in self.nodes if n.type == node_type]

    def get_assets_by_type(self, asset_type: str) -> list[ContentAsset]:
        """获取特定类型的所有资源"""
        return [a for a in self.assets if a.type == asset_type]

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "id": str(self.id),
            "media_type": self.media_type.value,
            "metadata": self.metadata.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "assets": [a.to_dict() for a in self.assets],
            "semantics": self.semantics.to_dict(),
            "source_path": self.source_path,
            "parsed_at": self.parsed_at.isoformat(),
            "confidence": self.confidence,
        }

    def checksum(self) -> str:
        """计算图谱的稳定校验和（DATA-CG-08）。

        用于回滚一致性验收（成功判据 #6）：patch 应用后再回滚，checksum 应与
        原始一致。只覆盖结构性字段（节点 id+类型+属性、边、资源 id+hash），
        不覆盖 parsed_at 等易变元数据。
        """
        import hashlib
        import json

        payload = {
            "nodes": sorted(
                (
                    {
                        "id": n.id,
                        "type": n.type.name,
                        "name": n.name,
                        "props": json.dumps(n.properties, sort_keys=True, default=str),
                    }
                    for n in self.nodes
                ),
                key=lambda x: x["id"],
            ),
            "edges": sorted(
                (
                    {
                        "s": e.source,
                        "t": e.target,
                        "y": e.type.value,
                    }
                    for e in self.edges
                ),
                key=lambda x: (x["s"], x["t"], x["y"]),
            ),
            "assets": sorted(
                (
                    {
                        "id": a.id,
                        "path": a.path,
                        "hash": a.hash,
                    }
                    for a in self.assets
                ),
                key=lambda x: x["id"],
            ),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def summary(self) -> str:
        """生成人类可读的内容摘要"""
        lines = [
            f"ContentGraph: {self.metadata.title or 'Untitled'}",
            f"  Media Type: {self.media_type.value}",
            f"  Engine: {self.metadata.engine.value if self.metadata.engine else 'unknown'}",
            f"  Nodes: {len(self.nodes)} ({len({n.type for n in self.nodes})} types)",
            f"  Edges: {len(self.edges)} ({len({e.type for e in self.edges})} types)",
            f"  Assets: {len(self.assets)} ({sum(a.size for a in self.assets) / (1024 * 1024):.1f} MB)",
            f"  Confidence: {self.confidence:.2f}",
        ]

        if self.semantics.summary:
            lines.append(f"  Summary: {self.semantics.summary[:100]}...")

        return "\n".join(lines)


# 辅助函数
def create_resource_node(name: str, path: str, **properties) -> ContentNode:
    """快速创建资源节点"""
    return ContentNode(
        type=NodeType.RESOURCE,
        name=name,
        properties=properties,
        source_path=path,
    )


def create_mechanic_node(name: str, description: str = "", **properties) -> ContentNode:
    """快速创建机制节点"""
    props = {"description": description, **properties}
    return ContentNode(
        type=NodeType.MECHANIC,
        name=name,
        properties=props,
    )
