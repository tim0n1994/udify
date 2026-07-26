"""
Udify Perception - Incremental Perception

增量感知：只重新解析变更的文件及其依赖，避免全量重建。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from udify.core.infrastructure.cache_manager import CacheManager
from udify.core.perception.parsers import INIParser, LuaParser, NPCScriptParser, OBJParser
from udify.models.content_graph import ContentGraph


@dataclass
class FileDependency:
    """文件依赖关系"""

    file_path: str
    depends_on: set[str] = field(default_factory=set)
    depended_by: set[str] = field(default_factory=set)
    last_modified: float = 0.0
    content_hash: str = ""


class DependencyGraph:
    """
    文件依赖图

    追踪文件间的依赖关系，支持增量更新。
    """

    def __init__(self) -> None:
        self._files: dict[str, FileDependency] = {}

    def add_file(self, file_path: str, depends_on: set[str] | None = None) -> None:
        """添加文件"""
        if file_path not in self._files:
            self._files[file_path] = FileDependency(file_path=file_path)

        dep = self._files[file_path]
        dep.last_modified = os.path.getmtime(file_path) if os.path.exists(file_path) else 0

        if depends_on:
            # 更新依赖关系
            for dep_file in depends_on:
                dep.depends_on.add(dep_file)
                if dep_file not in self._files:
                    self._files[dep_file] = FileDependency(file_path=dep_file)
                self._files[dep_file].depended_by.add(file_path)

    def get_affected_files(self, changed_files: set[str]) -> set[str]:
        """获取受变更影响的文件集合"""
        affected = set(changed_files)
        queue = list(changed_files)

        while queue:
            current = queue.pop(0)
            if current in self._files:
                # 找到所有依赖 current 的文件
                for dependent in self._files[current].depended_by:
                    if dependent not in affected:
                        affected.add(dependent)
                        queue.append(dependent)

        return affected

    def get_file_hash(self, file_path: str) -> str:
        """计算文件哈希"""
        if not os.path.exists(file_path):
            return ""
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def detect_changes(self, game_root: Path) -> set[str]:
        """检测变更的文件"""
        changed = set()

        for file_path, dep in self._files.items():
            full_path = game_root / file_path
            if not full_path.exists():
                # 文件被删除
                changed.add(file_path)
                continue

            current_mtime = os.path.getmtime(full_path)
            if current_mtime > dep.last_modified:
                # 文件可能被修改，检查哈希
                current_hash = self.get_file_hash(str(full_path))
                if current_hash != dep.content_hash:
                    changed.add(file_path)
                    dep.content_hash = current_hash
                    dep.last_modified = current_mtime

        return changed

    def to_dict(self) -> dict[str, Any]:
        """序列化"""
        return {
            file_path: {
                "depends_on": list(dep.depends_on),
                "depended_by": list(dep.depended_by),
                "last_modified": dep.last_modified,
                "content_hash": dep.content_hash,
            }
            for file_path, dep in self._files.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DependencyGraph:
        """反序列化"""
        graph = cls()
        for file_path, info in data.items():
            dep = FileDependency(
                file_path=file_path,
                depends_on=set(info.get("depends_on", [])),
                depended_by=set(info.get("depended_by", [])),
                last_modified=info.get("last_modified", 0),
                content_hash=info.get("content_hash", ""),
            )
            graph._files[file_path] = dep
        return graph


class IncrementalPerception:
    """
    增量感知引擎

    特性:
    - 首次全量感知
    - 后续增量更新（基于文件 mtime + hash）
    - 依赖追踪（变更文件 → 影响文件）
    - 缓存管理
    """

    def __init__(self, game_root: Path) -> None:
        self.game_root = game_root
        self.cache = CacheManager()
        self.dep_graph = DependencyGraph()
        self._is_first_run = True
        self._base_graph: ContentGraph | None = None

        # 初始化解析器
        self._ini_parser = INIParser()
        self._obj_parser = OBJParser()
        self._npc_parser = NPCScriptParser()
        self._lua_parser = LuaParser()

    async def perceive(self, game_root: Path | None = None) -> ContentGraph:
        """
        感知游戏目录

        首次调用时全量感知，后续调用时增量更新。
        """
        if game_root:
            self.game_root = game_root

        # 检查缓存
        cache_key = f"graph:{self.game_root}:{self._get_root_hash()}"
        cached = await self.cache.get(cache_key)

        if cached and not self._is_first_run:
            # 增量更新
            return await self._incremental_perceive(cached)

        # 全量感知
        graph = await self._full_perceive()
        self._base_graph = graph
        self._is_first_run = False

        # 缓存
        await self.cache.set(cache_key, graph)

        return graph

    async def _full_perceive(self) -> ContentGraph:
        """全量感知"""
        graph = ContentGraph()

        # 扫描所有文件
        for root, _, files in os.walk(self.game_root):
            for filename in files:
                file_path = Path(root) / filename
                rel_path = str(file_path.relative_to(self.game_root))

                # 解析文件
                await self._parse_file(file_path, rel_path, graph)

        return graph

    async def _incremental_perceive(self, cached_graph: ContentGraph) -> ContentGraph:
        """增量感知"""
        # 1. 检测变更文件
        changed_files = self.dep_graph.detect_changes(self.game_root)

        if not changed_files:
            # 无变更，返回缓存
            return cached_graph

        # 2. 计算受影响文件
        affected_files = self.dep_graph.get_affected_files(changed_files)

        # 3. 复制缓存图谱
        graph = self._copy_graph_except(cached_graph, affected_files)

        # 4. 重新解析受影响文件
        for file_path in affected_files:
            full_path = self.game_root / file_path
            if full_path.exists():
                await self._parse_file(full_path, file_path, graph)

        # 5. 更新缓存
        cache_key = f"graph:{self.game_root}:{self._get_root_hash()}"
        await self.cache.set(cache_key, graph)

        return graph

    async def _parse_file(self, file_path: Path, rel_path: str, graph: ContentGraph) -> None:
        """解析单个文件"""
        ext = file_path.suffix.lower()

        if ext == ".ini":
            self._ini_parser.parse(file_path, rel_path, graph)
        elif ext == ".obj":
            self._obj_parser.parse(file_path, rel_path, graph)
        elif ext in [".txt", ".npc"]:
            self._npc_parser.parse(file_path, rel_path, graph)
        elif ext == ".lua":
            self._lua_parser.parse(file_path, rel_path, graph)
        elif ext in [".asf", ".msf", ".mpc", ".map", ".mmf"]:
            await self._parse_binary_asset(file_path, rel_path, graph)

    async def _parse_binary_asset(
        self, file_path: Path, rel_path: str, graph: ContentGraph
    ) -> None:
        """解析二进制资产（miu2d 格式）"""
        try:
            raw = file_path.read_bytes()
        except Exception:
            return

        # 基于 miu2d 格式特征进行启发式解析
        ext = file_path.suffix.lower()

        # 提取文件头信息
        header = raw[:32]
        file_size = len(raw)

        # 创建资产节点
        sanitized = rel_path.replace("/", "_").replace("\\", "_").replace(".", "_")
        asset_id = f"asset_{sanitized}"

        from udify.models.content_graph import (
            ContentAsset,
            ContentEdge,
            ContentNode,
            EdgeType,
            NodeType,
        )

        # 解析 miu2d 特定格式
        properties: dict[str, Any] = {
            "file_size": file_size,
            "extension": ext,
            "header_hex": header[:8].hex(),
        }

        if ext == ".asf":
            # Audio Stream File
            properties["type"] = "audio"
            properties["format"] = self._detect_audio_format(raw)
        elif ext == ".msf":
            # Music Stream File
            properties["type"] = "music"
            properties["format"] = self._detect_audio_format(raw)
        elif ext == ".mpc":
            # MPC 压缩包
            properties["type"] = "archive"
            properties["entries"] = self._count_mpc_entries(raw)
        elif ext == ".map":
            # 地图文件
            properties["type"] = "map"
            properties["tile_data"] = self._extract_map_info(raw)
        elif ext == ".mmf":
            # 多媒体文件
            properties["type"] = "multimedia"
            properties["streams"] = self._count_mmf_streams(raw)
        elif ext == ".shd":
            # Shader 文件
            properties["type"] = "shader"
            properties["shader_text"] = self._extract_shader_text(raw)

        asset = ContentAsset(
            id=asset_id,
            path=rel_path,
            type=properties.get("type", "unknown"),
            format=properties.get("format", "binary"),
            metadata=properties,
        )
        graph.add_asset(asset)

        # 创建对应的资源节点
        node = ContentNode(
            id=asset_id,
            type=NodeType.RESOURCE,
            name=file_path.name,
            properties=properties,
            source_path=rel_path,
        )
        graph.add_node(node)

        # 建立文件到资产的包含关系
        file_node_id = f"file:{rel_path}"
        if not any(n.id == file_node_id for n in graph.nodes):
            file_node = ContentNode(
                id=file_node_id,
                type=NodeType.RESOURCE,
                name=rel_path,
                source_path=rel_path,
            )
            graph.add_node(file_node)

        graph.add_edge(
            ContentEdge(
                source=file_node_id,
                target=asset_id,
                type=EdgeType.CONTAINS,
            )
        )

    def _detect_audio_format(self, data: bytes) -> str:
        """检测音频格式"""
        if data[:4] == b"RIFF" or data[:4] == b"RIFX":
            return "wav"
        if data[:3] == b"ID3" or data[:2] == b"\xff\xfb" or data[:2] == b"\xff\xf3":
            return "mp3"
        if data[:4] == b"OggS":
            return "ogg"
        if data[:4] == b"fLaC":
            return "flac"
        return "unknown"

    def _count_mpc_entries(self, data: bytes) -> int:
        """统计 MPC 包中的条目数（启发式）"""
        # MPC 格式通常以文件头开始，后面跟随多个文件块
        # 简化实现：查找常见的文件签名
        count = 0
        signatures = [b"PK", b"RIFF", b"\x89PNG", b"BM", b"GIF"]
        for sig in signatures:
            count += data.count(sig)
        return max(1, count // 2)

    def _extract_map_info(self, data: bytes) -> dict[str, Any]:
        """提取地图信息（启发式）"""
        # 查找常见的地图维度模式
        info = {"width": 0, "height": 0, "layers": 0}
        # 尝试在前 256 字节中查找维度信息
        header = data[:256]
        # 常见的地图文件会有 width/height 的整数值
        for i in range(len(header) - 8):
            chunk = header[i : i + 8]
            # 查找合理的维度值（16-1024）
            vals = []
            for j in range(0, 8, 2):
                val = int.from_bytes(chunk[j : j + 2], "little")
                if 16 <= val <= 1024:
                    vals.append(val)
            if len(vals) >= 2:
                info["width"] = vals[0]
                info["height"] = vals[1]
                break
        return info

    def _count_mmf_streams(self, data: bytes) -> int:
        """统计 MMF 流数（启发式）"""
        # 统计常见的流头标记
        video_markers = data.count(b"vide") + data.count(b"VIDE")
        audio_markers = data.count(b"auds") + data.count(b"AUDS")
        return max(1, video_markers + audio_markers)

    def _extract_shader_text(self, data: bytes) -> str | None:
        """提取 Shader 文本（如果是文本格式）"""
        try:
            text = data.decode("utf-8", errors="ignore")
            # 检查是否像 shader 代码
            if "main" in text or "void" in text or "float" in text:
                return text[:500]
        except Exception:
            pass
        return None

    def _copy_graph_except(self, graph: ContentGraph, exclude_files: set[str]) -> ContentGraph:
        """复制图谱，排除指定文件相关的节点"""
        from copy import deepcopy

        new_graph = deepcopy(graph)

        # 移除与受影响文件相关的节点
        new_graph.nodes = [
            n for n in new_graph.nodes if not n.source_path or n.source_path not in exclude_files
        ]

        new_graph.edges = [
            e
            for e in new_graph.edges
            if e.source not in [n.id for n in new_graph.nodes if n.source_path in exclude_files]
        ]

        return new_graph

    def _get_root_hash(self) -> str:
        """获取游戏目录的哈希标识"""
        # 使用目录结构哈希
        files = sorted(Path(self.game_root).rglob("*"))
        content = "\n".join(str(f.relative_to(self.game_root)) for f in files if f.is_file())
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def invalidate_file(self, file_path: str) -> None:
        """手动失效文件缓存"""
        self.dep_graph.add_file(file_path)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "is_first_run": self._is_first_run,
            "dependency_count": len(self.dep_graph._files),
            "cached": self._base_graph is not None,
        }
