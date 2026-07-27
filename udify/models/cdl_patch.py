"""
Udify Core - CDL Patch/Diff System

CDL Patch 是 Udify 系统的核心输出格式。与完整重写不同，
它以结构化的 diff 方式描述对 ContentGraph 的修改，支持：

1. 可验证性：每个操作都可以独立验证
2. 可回滚：支持原子性应用和回滚
3. 可冲突检测：支持三路合并和冲突解决
4. 可审计：完整记录谁在何时做了什么修改

设计哲学：
- Patch 是 immutable 的（创建后不可变）
- 操作是原子的（要么成功，要么不影响图状态）
- 冲突是 first-class citizen（冲突本身被显式建模）
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from udify.models.source import SourceSpan

from udify.models.content_graph import (
    ContentAsset,
    ContentEdge,
    ContentGraph,
    ContentNode,
    EdgeType,
    NodeType,
)


class OpType(Enum):
    """操作类型"""

    ADD_NODE = "add_node"
    REMOVE_NODE = "remove_node"
    MODIFY_PROPERTY = "modify_property"
    ADD_EDGE = "add_edge"
    REMOVE_EDGE = "remove_edge"
    MODIFY_EDGE = "modify_edge"
    ADD_ASSET = "add_asset"
    REMOVE_ASSET = "remove_asset"
    MODIFY_ASSET = "modify_asset"


class ExecutionMode(Enum):
    """Patch 操作的执行形态（DATA-PATCH-01）。

    v3 把 Patch 从"仅图操作"扩展为一等执行形态：
    - ``graph_only``: 只改 ContentGraph（默认，向后兼容）。
    - ``file_patch``: 产生文件级修改（写入 VFS / 实际文件）。
    - ``runtime_hook``: 运行时注入（需沙箱 + 人工确认）。
    - ``package_overlay``: 打包成 ModPackage 覆盖层。
    """

    GRAPH_ONLY = "graph_only"
    FILE_PATCH = "file_patch"
    RUNTIME_HOOK = "runtime_hook"
    PACKAGE_OVERLAY = "package_overlay"


class ConflictType(Enum):
    """冲突类型"""

    SAME_NODE_REMOVE_VS_MODIFY = auto()  # A 删除节点，B 修改节点
    SAME_PROPERTY_MODIFY = auto()  # A 和 B 修改同一属性的不同值
    EDGE_SOURCE_REMOVED = auto()  # 边的源节点被删除
    EDGE_TARGET_REMOVED = auto()  # 边的目标节点被删除
    DUPLICATE_NODE_ID = auto()  # 添加已存在的节点 ID
    DUPLICATE_EDGE = auto()  # 添加已存在的边
    ASSET_REFERENCED_BY_NODE = auto()  # 资源被节点引用但已被删除
    CIRCULAR_DEPENDENCY = auto()  # 操作后产生循环依赖
    METADATA_MISMATCH = auto()  # 元数据冲突（如版本号）


@dataclass(frozen=True)
class PatchTarget:
    """图节点 ↔ SourceSpan 的双向锚定（DATA-PATCH-02）。

    让一个 PatchOperation 既能定位到 ContentGraph 中的节点/属性，又能定位到
    原始文件中的精确位置，保证"图操作"与"文件修改"可双向回溯。
    """

    node_id: str  # ContentGraph 节点 ID
    property_key: str | None = None  # 具体属性键（MODIFY_PROPERTY 用）
    file_path: str = ""  # SourceSpan.file_path
    span_line_start: int | None = None
    span_line_end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "property_key": self.property_key,
            "file_path": self.file_path,
            "span_line_start": self.span_line_start,
            "span_line_end": self.span_line_end,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchTarget:
        return cls(
            node_id=data["node_id"],
            property_key=data.get("property_key"),
            file_path=data.get("file_path", ""),
            span_line_start=data.get("span_line_start"),
            span_line_end=data.get("span_line_end"),
        )


@dataclass(frozen=True)
class PatchOperation:
    """
    Patch 操作基类

    frozen=True 保证操作是不可变的，这是可审计性和可重放性的基础。
    """

    op_type: OpType
    target_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    # v3 扩展（optional，向后兼容；DATA-PATCH-01..06）
    execution_mode: ExecutionMode = ExecutionMode.GRAPH_ONLY
    source_span: SourceSpan | None = None
    risk: float = 0.0  # 0.0–1.0 启发式风险分（R0–R4 的连续化）
    planning_reason: str = ""  # 可解释性：为何规划此操作
    validation_probes: tuple[Any, ...] = field(default_factory=tuple)  # ProbeSpec，先可空
    # v3 双向锚定 + 条件 + 逆操作（DATA-PATCH-02..06）
    patch_target: PatchTarget | None = None  # 图节点 ↔ SourceSpan 双向锚定
    preconditions: tuple[str, ...] = field(default_factory=tuple)  # 应用前必须满足的条件
    postconditions: tuple[str, ...] = field(default_factory=tuple)  # 应用后必须成立的条件
    reverse: PatchOperation | None = None  # 预计算的逆操作（PATCH-SYN-06）

    def __post_init__(self) -> None:
        # 验证 payload 类型
        if not isinstance(self.payload, dict):
            object.__setattr__(self, "payload", {"_raw": self.payload})

    def __hash__(self) -> int:
        """自定义哈希函数，处理 dict 字段"""
        return hash(
            (
                self.op_type,
                self.target_id,
                self._hashable_payload(self.payload),
            )
        )

    @staticmethod
    def _hashable_payload(obj: Any) -> Any:
        """将任意对象转换为可哈希形式"""
        if isinstance(obj, dict):
            return tuple((k, PatchOperation._hashable_payload(v)) for k, v in sorted(obj.items()))
        elif isinstance(obj, list):
            return tuple(PatchOperation._hashable_payload(x) for x in obj)
        elif isinstance(obj, set):
            return tuple(sorted(PatchOperation._hashable_payload(x) for x in obj))
        return obj

    def to_dict(self) -> dict[str, Any]:
        """完整序列化（含 v3 字段）。

        v3 字段只在非默认值时输出，保证与旧格式的 JSON 兼容且体积小；
        证据链（source_span/patch_target/reverse/risk）必须经得起落盘往返
        （ADR-v3-004 Evidence-first——审阅与应用之间隔着一次持久化）。
        """
        d: dict[str, Any] = {
            "op_type": self.op_type.name,
            "target_id": self.target_id,
            "payload": self.payload,
        }
        if self.execution_mode is not ExecutionMode.GRAPH_ONLY:
            d["execution_mode"] = self.execution_mode.name
        if self.source_span is not None:
            d["source_span"] = self.source_span.to_dict()
        if self.risk:
            d["risk"] = self.risk
        if self.planning_reason:
            d["planning_reason"] = self.planning_reason
        if self.patch_target is not None:
            d["patch_target"] = self.patch_target.to_dict()
        if self.preconditions:
            d["preconditions"] = list(self.preconditions)
        if self.postconditions:
            d["postconditions"] = list(self.postconditions)
        if self.reverse is not None:
            d["reverse"] = self.reverse.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchOperation:
        """从字典还原（v3 字段可选，旧格式兼容）。"""
        from udify.models.source import SourceSpan  # 顶层 TYPE_CHECKING，运行时局部导入避免环

        reverse_data = data.get("reverse")
        span_data = data.get("source_span")
        target_data = data.get("patch_target")
        return cls(
            op_type=OpType[data["op_type"]],
            target_id=data["target_id"],
            payload=data.get("payload", {}),
            execution_mode=ExecutionMode[data["execution_mode"]]
            if "execution_mode" in data
            else ExecutionMode.GRAPH_ONLY,
            source_span=SourceSpan.from_dict(span_data) if span_data else None,
            risk=float(data.get("risk", 0.0)),
            planning_reason=data.get("planning_reason", ""),
            patch_target=PatchTarget.from_dict(target_data) if target_data else None,
            preconditions=tuple(data.get("preconditions", ())),
            postconditions=tuple(data.get("postconditions", ())),
            reverse=cls.from_dict(reverse_data) if reverse_data else None,
        )


@dataclass
class PatchConflict:
    """Patch 冲突"""

    conflict_type: ConflictType
    operation_a: PatchOperation | None
    operation_b: PatchOperation | None
    description: str
    severity: str = "error"  # error, warning, info

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_type": self.conflict_type.name,
            "operation_a": {
                "op_type": self.operation_a.op_type.name,
                "target_id": self.operation_a.target_id,
            }
            if self.operation_a
            else None,
            "operation_b": {
                "op_type": self.operation_b.op_type.name,
                "target_id": self.operation_b.target_id,
            }
            if self.operation_b
            else None,
            "description": self.description,
            "severity": self.severity,
        }


@dataclass
class CDLPatch:
    """
    CDL Patch - 对 ContentGraph 的结构化修改

    类似于 Git commit，但针对内容图谱而非文本文件。
    每个 Patch 包含：
    - 一系列原子操作
    - 元数据（作者、意图、时间戳、父版本）
    - 可选的冲突列表（合并时产生）

    Attributes:
        operations: 有序的操作列表
        intent: 修改意图描述（自然语言，用于可解释性）
        author: 修改者标识（人类用户名或 AI agent ID）
        created_at: 创建时间
        parent_hash: 父版本哈希（用于链式版本控制）
        patch_id: 唯一标识符
        conflicts: 合并时产生的冲突（应用前必须解决）
    """

    operations: list[PatchOperation] = field(default_factory=list)
    intent: str = ""
    author: str = "unknown"
    created_at: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))
    parent_hash: str | None = None
    patch_id: str = field(default_factory=lambda: str(uuid4()))
    conflicts: list[PatchConflict] = field(default_factory=list)

    # 运行时状态（不序列化）
    _applied: bool = field(default=False, repr=False)
    _original_state: dict[str, Any] | None = field(default=None, repr=False)

    def add_operation(self, op: PatchOperation) -> CDLPatch:
        """添加操作并返回 self（链式调用）"""
        self.operations.append(op)
        return self

    def is_empty(self) -> bool:
        """检查是否为空 patch"""
        return len(self.operations) == 0

    def has_conflicts(self) -> bool:
        """检查是否有未解决的冲突"""
        return any(c.severity == "error" for c in self.conflicts)

    def summary(self) -> str:
        """生成人类可读的摘要"""
        lines = [
            f"CDLPatch[{self.patch_id[:8]}] by {self.author}",
            f"  Intent: {self.intent[:60]}{'...' if len(self.intent) > 60 else ''}",
            f"  Operations: {len(self.operations)}",
        ]

        # 统计各类型操作
        counts: dict[str, int] = {}
        for op in self.operations:
            name = op.op_type.name
            counts[name] = counts.get(name, 0) + 1
        for op_type, count in sorted(counts.items()):
            lines.append(f"    - {op_type}: {count}")

        if self.conflicts:
            lines.append(
                f"  Conflicts: {len(self.conflicts)} ({sum(1 for c in self.conflicts if c.severity == 'error')} errors)"
            )

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "patch_id": self.patch_id,
            "intent": self.intent,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "parent_hash": self.parent_hash,
            "operations": [op.to_dict() for op in self.operations],
            "conflicts": [c.to_dict() for c in self.conflicts],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CDLPatch:
        """从字典反序列化"""
        patch = cls(
            intent=data.get("intent", ""),
            author=data.get("author", "unknown"),
            parent_hash=data.get("parent_hash"),
            patch_id=data.get("patch_id", str(uuid4())),
        )

        if "created_at" in data and data["created_at"]:
            patch.created_at = datetime.fromisoformat(data["created_at"])

        for op_data in data.get("operations", []):
            patch.operations.append(PatchOperation.from_dict(op_data))

        return patch


class PatchValidator:
    """
    Patch 验证器

    在应用 patch 之前进行静态验证，检测：
    1. 操作引用的节点/边/资源是否存在（或不存在）
    2. 操作是否会导致图的不一致性
    3. 操作之间是否有内部冲突
    """

    def validate(self, patch: CDLPatch, graph: ContentGraph) -> list[PatchConflict]:
        """
        验证 patch 是否可以在给定图上安全应用

        Returns:
            冲突列表。空列表表示验证通过。
        """
        conflicts: list[PatchConflict] = []

        # 收集操作影响的对象 ID
        removed_nodes: set[str] = set()
        removed_edges: set[tuple[str, str, EdgeType]] = set()
        removed_assets: set[str] = set()
        modified_properties: dict[str, dict[str, Any]] = {}  # node_id -> {prop_key: value}
        added_node_ids: set[str] = set()
        added_edges: set[tuple[str, str, EdgeType]] = set()

        for op in patch.operations:
            # 检查重复添加
            if op.op_type == OpType.ADD_NODE:
                node_id = op.payload.get("node_id", op.target_id)
                if node_id in added_node_ids:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.DUPLICATE_NODE_ID,
                            operation_a=op,
                            operation_b=None,
                            description=f"Duplicate node ID in patch: {node_id}",
                        )
                    )
                added_node_ids.add(node_id)

                # 检查是否已存在于图中
                if graph.get_node(node_id) is not None:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.DUPLICATE_NODE_ID,
                            operation_a=op,
                            operation_b=None,
                            description=f"Node {node_id} already exists in graph",
                            severity="warning",
                        )
                    )

            elif op.op_type == OpType.REMOVE_NODE:
                removed_nodes.add(op.target_id)

                # 检查节点是否存在
                if graph.get_node(op.target_id) is None:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.SAME_NODE_REMOVE_VS_MODIFY,
                            operation_a=op,
                            operation_b=None,
                            description=f"Cannot remove non-existent node: {op.target_id}",
                        )
                    )

            elif op.op_type == OpType.MODIFY_PROPERTY:
                if op.target_id in removed_nodes:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.SAME_NODE_REMOVE_VS_MODIFY,
                            operation_a=op,
                            operation_b=None,
                            description=f"Cannot modify properties of removed node: {op.target_id}",
                        )
                    )

                # 检查属性重复修改
                prop_key = op.payload.get("key")
                if prop_key:
                    if op.target_id not in modified_properties:
                        modified_properties[op.target_id] = {}
                    if prop_key in modified_properties[op.target_id]:
                        conflicts.append(
                            PatchConflict(
                                conflict_type=ConflictType.SAME_PROPERTY_MODIFY,
                                operation_a=op,
                                operation_b=None,
                                description=f"Property '{prop_key}' on node '{op.target_id}' modified multiple times in same patch",
                                severity="warning",
                            )
                        )
                    modified_properties[op.target_id][prop_key] = op.payload.get("value")

            elif op.op_type == OpType.ADD_EDGE:
                edge_key = (
                    op.payload.get("source", op.target_id),
                    op.payload.get("target", ""),
                    EdgeType[op.payload.get("edge_type", "DEPENDS_ON")],
                )
                if edge_key in added_edges:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.DUPLICATE_EDGE,
                            operation_a=op,
                            operation_b=None,
                            description=f"Duplicate edge in patch: {edge_key}",
                        )
                    )
                added_edges.add(edge_key)

            elif op.op_type == OpType.REMOVE_EDGE:
                removed_edges.add(
                    (
                        op.payload.get("source", op.target_id),
                        op.payload.get("target", ""),
                        EdgeType[op.payload.get("edge_type", "DEPENDS_ON")],
                    )
                )

            elif op.op_type == OpType.ADD_ASSET:
                asset_id = op.payload.get("asset_id", op.target_id)
                if any(a.id == asset_id for a in graph.assets):
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.DUPLICATE_NODE_ID,
                            operation_a=op,
                            operation_b=None,
                            description=f"Asset {asset_id} already exists in graph",
                            severity="warning",
                        )
                    )

            elif op.op_type == OpType.REMOVE_ASSET:
                removed_assets.add(op.target_id)

        # 第二阶段：检查边与节点的交叉引用
        for op in patch.operations:
            if op.op_type == OpType.ADD_EDGE:
                source = op.payload.get("source", op.target_id)
                target = op.payload.get("target", "")

                # 检查源节点是否会被删除
                if source in removed_nodes:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.EDGE_SOURCE_REMOVED,
                            operation_a=op,
                            operation_b=None,
                            description=f"Edge source node '{source}' is removed in the same patch",
                        )
                    )

                # 检查目标节点是否会被删除
                if target in removed_nodes:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.EDGE_TARGET_REMOVED,
                            operation_a=op,
                            operation_b=None,
                            description=f"Edge target node '{target}' is removed in the same patch",
                        )
                    )

                # 检查节点是否存在（如果不在添加列表中）
                if source not in added_node_ids and graph.get_node(source) is None:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.EDGE_SOURCE_REMOVED,
                            operation_a=op,
                            operation_b=None,
                            description=f"Edge source node '{source}' does not exist",
                        )
                    )

                if target not in added_node_ids and graph.get_node(target) is None:
                    conflicts.append(
                        PatchConflict(
                            conflict_type=ConflictType.EDGE_TARGET_REMOVED,
                            operation_a=op,
                            operation_b=None,
                            description=f"Edge target node '{target}' does not exist",
                        )
                    )

        return conflicts


class PatchApplicator:
    """
    Patch 应用器

    负责将 CDLPatch 应用到 ContentGraph，支持：
    1. 原子性应用（所有操作成功或都不应用）
    2. 回滚（恢复到应用前的状态）
    3. 增量应用（只应用部分操作）
    """

    def __init__(self) -> None:
        self.validator = PatchValidator()
        self._history: list[tuple[str, dict[str, Any]]] = []  # (patch_id, snapshot)

    def apply(
        self,
        patch: CDLPatch,
        graph: ContentGraph,
        validate: bool = True,
        atomic: bool = True,
    ) -> tuple[bool, list[PatchConflict]]:
        """
        应用 patch 到图

        Args:
            patch: 要应用的 patch
            graph: 目标图
            validate: 是否先验证
            atomic: 是否原子性应用（失败时回滚）

        Returns:
            (是否成功, 冲突列表)
        """
        if validate:
            conflicts = self.validator.validate(patch, graph)
            if any(c.severity == "error" for c in conflicts):
                patch.conflicts = conflicts
                return False, conflicts

        # 保存原始状态用于回滚
        snapshot = self._snapshot(graph)
        patch._original_state = snapshot

        applied_ops: list[PatchOperation] = []

        try:
            for op in patch.operations:
                self._apply_operation(op, graph)
                applied_ops.append(op)

            patch._applied = True
            self._history.append((patch.patch_id, snapshot))
            return True, []

        except Exception as e:
            if atomic:
                # 回滚已应用的操作
                self._restore(graph, snapshot)
                patch._applied = False

            error_conflict = PatchConflict(
                conflict_type=ConflictType.METADATA_MISMATCH,
                operation_a=applied_ops[-1] if applied_ops else None,
                operation_b=None,
                description=f"Application failed at operation {len(applied_ops)}: {str(e)}",
            )
            return False, [error_conflict]

    def rollback(self, patch: CDLPatch, graph: ContentGraph) -> bool:
        """
        回滚 patch

        Args:
            patch: 要回滚的 patch
            graph: 目标图

        Returns:
            是否成功回滚
        """
        if not patch._applied or patch._original_state is None:
            return False

        self._restore(graph, patch._original_state)
        patch._applied = False
        return True

    def _apply_operation(self, op: PatchOperation, graph: ContentGraph) -> None:
        """应用单个操作"""
        if op.op_type == OpType.ADD_NODE:
            node = ContentNode(
                id=op.payload.get("node_id", op.target_id),
                type=NodeType[op.payload.get("node_type", "RESOURCE")],
                name=op.payload.get("name", ""),
                properties=op.payload.get("properties", {}),
                media_type=graph.media_type,
                source_path=op.payload.get("source_path"),
            )
            graph.add_node(node)

        elif op.op_type == OpType.REMOVE_NODE:
            node = graph.get_node(op.target_id)
            if node is None:
                raise ValueError(f"Node not found: {op.target_id}")

            # 移除相关边
            graph.edges = [
                e for e in graph.edges if e.source != op.target_id and e.target != op.target_id
            ]
            # 移除节点
            graph.nodes = [n for n in graph.nodes if n.id != op.target_id]

        elif op.op_type == OpType.MODIFY_PROPERTY:
            node = graph.get_node(op.target_id)
            if node is None:
                raise ValueError(f"Node not found: {op.target_id}")

            key = op.payload.get("key")
            value = op.payload.get("value")
            if key is not None:
                node.properties[key] = value

        elif op.op_type == OpType.ADD_EDGE:
            edge = ContentEdge(
                source=op.payload.get("source", op.target_id),
                target=op.payload.get("target", ""),
                type=EdgeType[op.payload.get("edge_type", "DEPENDS_ON")],
                weight=op.payload.get("weight", 1.0),
                properties=op.payload.get("properties", {}),
            )
            graph.add_edge(edge)

        elif op.op_type == OpType.REMOVE_EDGE:
            source = op.payload.get("source", op.target_id)
            target = op.payload.get("target", "")
            edge_type = EdgeType[op.payload.get("edge_type", "DEPENDS_ON")]

            graph.edges = [
                e
                for e in graph.edges
                if not (e.source == source and e.target == target and e.type == edge_type)
            ]

        elif op.op_type == OpType.MODIFY_EDGE:
            source = op.payload.get("source", op.target_id)
            target = op.payload.get("target", "")
            edge_type = EdgeType[op.payload.get("edge_type", "DEPENDS_ON")]

            for edge in graph.edges:
                if edge.source == source and edge.target == target and edge.type == edge_type:
                    if "weight" in op.payload:
                        edge.weight = op.payload["weight"]
                    if "properties" in op.payload:
                        edge.properties.update(op.payload["properties"])
                    break
            else:
                raise ValueError(f"Edge not found: {source} -> {target} ({edge_type})")

        elif op.op_type == OpType.ADD_ASSET:
            asset = ContentAsset(
                id=op.payload.get("asset_id", op.target_id),
                path=op.payload.get("path", ""),
                type=op.payload.get("type", ""),
                format=op.payload.get("format", ""),
                size=op.payload.get("size", 0),
                hash=op.payload.get("hash"),
            )
            graph.add_asset(asset)

        elif op.op_type == OpType.REMOVE_ASSET:
            graph.assets = [a for a in graph.assets if a.id != op.target_id]

        elif op.op_type == OpType.MODIFY_ASSET:
            for asset in graph.assets:
                if asset.id == op.target_id:
                    if "path" in op.payload:
                        asset.path = op.payload["path"]
                    if "type" in op.payload:
                        asset.type = op.payload["type"]
                    if "format" in op.payload:
                        asset.format = op.payload["format"]
                    if "hash" in op.payload:
                        asset.hash = op.payload["hash"]
                    break
            else:
                raise ValueError(f"Asset not found: {op.target_id}")

    def _snapshot(self, graph: ContentGraph) -> dict[str, Any]:
        """创建图的深度拷贝快照"""
        return {
            "nodes": deepcopy(graph.nodes),
            "edges": deepcopy(graph.edges),
            "assets": deepcopy(graph.assets),
            "metadata": deepcopy(graph.metadata),
            "semantics": deepcopy(graph.semantics),
        }

    def _restore(self, graph: ContentGraph, snapshot: dict[str, Any]) -> None:
        """从快照恢复图"""
        graph.nodes = snapshot["nodes"]
        graph.edges = snapshot["edges"]
        graph.assets = snapshot["assets"]
        graph.metadata = snapshot["metadata"]
        graph.semantics = snapshot["semantics"]


class GraphDiffer:
    """
    图差异计算器

    计算两个 ContentGraph 之间的差异，生成 CDLPatch。
    这是"逆向工程"的关键工具：给定原始图和修改后的图，
    生成描述修改的 patch。
    """

    def diff(self, old_graph: ContentGraph, new_graph: ContentGraph, intent: str = "") -> CDLPatch:
        """
        计算两个图之间的差异

        Args:
            old_graph: 原始图
            new_graph: 修改后的图
            intent: 修改意图描述

        Returns:
            描述差异的 CDLPatch
        """
        patch = CDLPatch(intent=intent, author="graph_differ")

        # 节点差异
        old_node_ids = {n.id for n in old_graph.nodes}
        new_node_ids = {n.id for n in new_graph.nodes}

        # 新增的节点
        for node in new_graph.nodes:
            if node.id not in old_node_ids:
                patch.add_operation(
                    PatchOperation(
                        op_type=OpType.ADD_NODE,
                        target_id=node.id,
                        payload={
                            "node_id": node.id,
                            "node_type": node.type.name,
                            "name": node.name,
                            "properties": node.properties,
                            "source_path": node.source_path,
                        },
                    )
                )

        # 删除的节点
        for node in old_graph.nodes:
            if node.id not in new_node_ids:
                patch.add_operation(
                    PatchOperation(
                        op_type=OpType.REMOVE_NODE,
                        target_id=node.id,
                    )
                )

        # 修改的节点（属性变化）
        old_nodes = {n.id: n for n in old_graph.nodes}
        new_nodes = {n.id: n for n in new_graph.nodes}

        for node_id in old_node_ids & new_node_ids:
            old_node = old_nodes[node_id]
            new_node = new_nodes[node_id]

            # 检查属性变化
            all_keys = set(old_node.properties.keys()) | set(new_node.properties.keys())
            for key in all_keys:
                old_val = old_node.properties.get(key)
                new_val = new_node.properties.get(key)

                if old_val != new_val:
                    patch.add_operation(
                        PatchOperation(
                            op_type=OpType.MODIFY_PROPERTY,
                            target_id=node_id,
                            payload={
                                "key": key,
                                "old_value": old_val,
                                "value": new_val,
                            },
                        )
                    )

        # 边差异
        old_edges = {(e.source, e.target, e.type): e for e in old_graph.edges}
        new_edges = {(e.source, e.target, e.type): e for e in new_graph.edges}

        # 新增的边
        for key, edge in new_edges.items():
            if key not in old_edges:
                patch.add_operation(
                    PatchOperation(
                        op_type=OpType.ADD_EDGE,
                        target_id=edge.source,
                        payload={
                            "source": edge.source,
                            "target": edge.target,
                            "edge_type": edge.type.name,
                            "weight": edge.weight,
                            "properties": edge.properties,
                        },
                    )
                )

        # 删除的边
        for key, edge in old_edges.items():
            if key not in new_edges:
                patch.add_operation(
                    PatchOperation(
                        op_type=OpType.REMOVE_EDGE,
                        target_id=edge.source,
                        payload={
                            "source": edge.source,
                            "target": edge.target,
                            "edge_type": edge.type.name,
                        },
                    )
                )

        # 资源差异
        old_assets = {a.id: a for a in old_graph.assets}
        new_assets = {a.id: a for a in new_graph.assets}

        for asset_id in set(new_assets.keys()) - set(old_assets.keys()):
            asset = new_assets[asset_id]
            patch.add_operation(
                PatchOperation(
                    op_type=OpType.ADD_ASSET,
                    target_id=asset_id,
                    payload=asset.to_dict(),
                )
            )

        for asset_id in set(old_assets.keys()) - set(new_assets.keys()):
            patch.add_operation(
                PatchOperation(
                    op_type=OpType.REMOVE_ASSET,
                    target_id=asset_id,
                )
            )

        return patch


# 便捷函数
def create_add_node_op(
    node_id: str,
    node_type: NodeType,
    name: str,
    properties: dict[str, Any] | None = None,
    source_path: str | None = None,
) -> PatchOperation:
    """创建添加节点操作"""
    return PatchOperation(
        op_type=OpType.ADD_NODE,
        target_id=node_id,
        payload={
            "node_id": node_id,
            "node_type": node_type.name,
            "name": name,
            "properties": properties or {},
            "source_path": source_path,
        },
    )


def create_remove_node_op(node_id: str) -> PatchOperation:
    """创建删除节点操作"""
    return PatchOperation(
        op_type=OpType.REMOVE_NODE,
        target_id=node_id,
    )


def create_modify_property_op(
    node_id: str,
    key: str,
    value: Any,
) -> PatchOperation:
    """创建修改属性操作"""
    return PatchOperation(
        op_type=OpType.MODIFY_PROPERTY,
        target_id=node_id,
        payload={
            "key": key,
            "value": value,
        },
    )


def create_add_edge_op(
    source: str,
    target: str,
    edge_type: EdgeType = EdgeType.DEPENDS_ON,
    weight: float = 1.0,
    properties: dict[str, Any] | None = None,
) -> PatchOperation:
    """创建添加边操作"""
    return PatchOperation(
        op_type=OpType.ADD_EDGE,
        target_id=source,
        payload={
            "source": source,
            "target": target,
            "edge_type": edge_type.name,
            "weight": weight,
            "properties": properties or {},
        },
    )


def create_remove_edge_op(
    source: str,
    target: str,
    edge_type: EdgeType = EdgeType.DEPENDS_ON,
) -> PatchOperation:
    """创建删除边操作"""
    return PatchOperation(
        op_type=OpType.REMOVE_EDGE,
        target_id=source,
        payload={
            "source": source,
            "target": target,
            "edge_type": edge_type.name,
        },
    )


def create_add_asset_op(
    asset_id: str,
    path: str,
    asset_type: str,
    format: str,
    **kwargs: Any,
) -> PatchOperation:
    """创建添加资源操作"""
    payload = {
        "asset_id": asset_id,
        "path": path,
        "type": asset_type,
        "format": format,
        **kwargs,
    }
    return PatchOperation(
        op_type=OpType.ADD_ASSET,
        target_id=asset_id,
        payload=payload,
    )


def create_remove_asset_op(asset_id: str) -> PatchOperation:
    """创建删除资源操作"""
    return PatchOperation(
        op_type=OpType.REMOVE_ASSET,
        target_id=asset_id,
    )
