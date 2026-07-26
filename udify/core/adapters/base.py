"""
引擎适配器协议（v3 引擎抽象）。

对应 ITERATION-PLAN-2026-07.md §4.2「引擎适配器协议（把硬编码变契约）」与
任务 ``ADAPT-ENGINE-01..04``。

目标：把"检测引擎 → 感知 → 动作 schema → 发射 patch → 运行时探针 → 打包"
统一成一份契约，任何新引擎（RPG Maker MV/MZ、Unity…）都通过实现同一协议接入，
无需重讲架构。miu2d 是首个实现（见 ``miu2d.py``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from udify.models.content_graph import ContentGraph
from udify.models.source import Confidence, SourceSpan


@dataclass
class DetectionResult:
    """引擎检测结果（ADAPT-ENGINE-01）。

    Attributes:
        engine_id: 引擎标识（如 ``miu2d``、``rpg_maker_mv``）。
        confidence: 检测置信度。
        evidence: 支撑检测的证据（文件签名、manifest 等）。
        supported_operations: 该引擎支持的修改操作类型。
    """

    engine_id: str
    confidence: Confidence
    evidence: list[str] = field(default_factory=list)
    supported_operations: list[str] = field(default_factory=list)


@runtime_checkable
class EngineAdapter(Protocol):
    """引擎适配器协议（ADAPT-ENGINE-02..04）。

    每个引擎适配器实现这六个能力。协议用 ``Protocol`` 定义，miu2d 等具体
    适配器只需鸭子类型实现，无需继承。
    """

    @property
    def engine_id(self) -> str:
        """引擎唯一标识。"""
        ...

    def detect(self, game_root: Path) -> DetectionResult:
        """检测 game_root 是否为本引擎，返回置信度与证据。"""
        ...

    def perceive(self, game_root: Path) -> ContentGraph:
        """感知 game_root，输出带 SourceSpan 的 ContentGraph。"""
        ...

    def get_action_schemas(self) -> list[dict[str, Any]]:
        """返回本引擎支持的动作 schema（供 planner/action_space 使用）。"""
        ...

    def emit_patch(self, graph: ContentGraph, actions: list[Any]) -> list[Any]:
        """把规划动作发射为该引擎具体的 PatchOperation（带 execution_mode）。"""
        ...

    def build_runtime_probes(self, graph: ContentGraph) -> list[dict[str, Any]]:
        """为运行时验证构造探针规格（ProbeSpec）。"""
        ...

    def package_mod(self, graph: ContentGraph, patch_ops: list[Any], output_dir: Path) -> Path:
        """把修改打包成该引擎的 ModPackage，返回产物路径。"""
        ...


def span_for_node(file_path: str, node_id: str, extractor_id: str = "unknown") -> SourceSpan:
    """便捷工具：为节点构造一个最小 SourceSpan。"""
    from udify.models.source import ToolRunRef

    return SourceSpan(
        file_path=file_path,
        extractor=ToolRunRef(tool_id=extractor_id),
        ast_path=(node_id,),
    )


__all__ = ["DetectionResult", "EngineAdapter", "span_for_node"]
