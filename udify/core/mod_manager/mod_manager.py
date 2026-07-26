"""
Udify Mod Manager - Multi-Mod Manager

多 Mod 管理器：管理多个 Mod 的安装、卸载、冲突解决。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class ModStatus(Enum):
    """Mod 状态"""

    DRAFT = auto()
    INSTALLED = auto()
    ACTIVE = auto()
    DISABLED = auto()
    CONFLICT = auto()
    ERROR = auto()


@dataclass
class ModConflict:
    """Mod 冲突"""

    conflict_type: str  # file_collision, semantic_conflict, dependency_missing
    mod_a: str
    mod_b: str
    description: str
    file_path: str | None = None
    severity: str = "error"  # warning, error, critical

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_type": self.conflict_type,
            "mod_a": self.mod_a,
            "mod_b": self.mod_b,
            "description": self.description,
            "file_path": self.file_path,
            "severity": self.severity,
        }


@dataclass
class InstalledMod:
    """已安装的 Mod"""

    mod_id: str
    name: str
    version: str
    author: str
    status: ModStatus = ModStatus.INSTALLED
    install_order: int = 0
    install_time: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))
    files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    conflicts: list[ModConflict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mod_id": self.mod_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "status": self.status.name,
            "install_order": self.install_order,
            "install_time": self.install_time.isoformat(),
            "files": self.files,
            "dependencies": self.dependencies,
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


@dataclass
class ModStack:
    """Mod 堆栈"""

    mods: list[InstalledMod]
    load_order: list[str]
    conflicts: list[ModConflict]
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mods": [m.to_dict() for m in self.mods],
            "load_order": self.load_order,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "is_valid": self.is_valid,
        }


@dataclass
class InstallResult:
    """安装结果"""

    success: bool
    mod_id: str
    conflicts: list[ModConflict]
    errors: list[str]
    installed_files: list[str]


@dataclass
class UninstallResult:
    """卸载结果"""

    success: bool
    mod_id: str
    removed_files: list[str]
    reverted_files: list[str]
    errors: list[str]


class ConflictResolver:
    """
    冲突解决器

    支持:
    - 文件级冲突检测
    - 语义级冲突检测
    - 自动冲突解决（基于优先级）
    """

    def resolve(self, conflicts: list[ModConflict]) -> ConflictResolution:
        """解决冲突"""
        resolved = []
        unresolved = []

        for conflict in conflicts:
            if conflict.conflict_type == "file_collision":
                # 文件冲突：后安装的 Mod 优先
                resolved.append(conflict)
            elif conflict.conflict_type == "semantic_conflict":
                # 语义冲突：需要人工介入
                if conflict.severity == "warning":
                    resolved.append(conflict)
                else:
                    unresolved.append(conflict)
            elif conflict.conflict_type == "dependency_missing":
                # 依赖缺失：无法自动解决
                unresolved.append(conflict)
            else:
                unresolved.append(conflict)

        return ConflictResolution(
            resolved=resolved,
            unresolved=unresolved,
            success=len(unresolved) == 0,
        )


@dataclass
class ConflictResolution:
    """冲突解决结果"""

    resolved: list[ModConflict]
    unresolved: list[ModConflict]
    success: bool


class MultiModManager:
    """
    多 Mod 管理器

    管理 Mod 的生命周期：
    - 安装（依赖检查、冲突检测）
    - 卸载（回滚、重新应用后续 Mod）
    - 激活/禁用
    - 冲突解决
    """

    def __init__(self, game_root: str) -> None:
        self.game_root = game_root
        self._installed: dict[str, InstalledMod] = {}
        self._load_order: list[str] = []
        self._conflict_resolver = ConflictResolver()
        self._backup_dir = ".udify/backups"

    async def install_mod(
        self,
        mod_id: str,
        name: str,
        version: str,
        author: str,
        files: list[str],
        dependencies: list[str] | None = None,
    ) -> InstallResult:
        """安装 Mod"""
        dependencies = dependencies or []
        errors = []
        conflicts = []

        # 1. 检查依赖
        for dep_id in dependencies:
            if dep_id not in self._installed:
                errors.append(f"缺少依赖: {dep_id}")
                return InstallResult(
                    success=False,
                    mod_id=mod_id,
                    conflicts=[],
                    errors=errors,
                    installed_files=[],
                )

        # 2. 检查冲突
        for existing_id, existing_mod in self._installed.items():
            file_conflicts = set(files) & set(existing_mod.files)
            if file_conflicts:
                for f in file_conflicts:
                    conflicts.append(
                        ModConflict(
                            conflict_type="file_collision",
                            mod_a=mod_id,
                            mod_b=existing_id,
                            description=f"文件冲突: {f}",
                            file_path=f,
                            severity="error",
                        )
                    )

        # 3. 尝试解决冲突
        if conflicts:
            resolution = self._conflict_resolver.resolve(conflicts)
            if not resolution.success:
                return InstallResult(
                    success=False,
                    mod_id=mod_id,
                    conflicts=resolution.unresolved,
                    errors=["冲突无法自动解决"],
                    installed_files=[],
                )
            # 即使有 resolved 的冲突，如果 severity 为 error，也标记为不完全成功
            if any(c.severity == "error" for c in conflicts):
                return InstallResult(
                    success=False,
                    mod_id=mod_id,
                    conflicts=conflicts,
                    errors=["检测到严重冲突"],
                    installed_files=[],
                )

        # 4. 创建 Mod 记录
        install_order = len(self._load_order)
        mod = InstalledMod(
            mod_id=mod_id,
            name=name,
            version=version,
            author=author,
            install_order=install_order,
            files=files,
            dependencies=dependencies,
            conflicts=conflicts,
        )

        self._installed[mod_id] = mod
        self._load_order.append(mod_id)

        return InstallResult(
            success=True,
            mod_id=mod_id,
            conflicts=conflicts,
            errors=errors,
            installed_files=files,
        )

    async def uninstall_mod(self, mod_id: str) -> UninstallResult:
        """卸载 Mod"""
        if mod_id not in self._installed:
            return UninstallResult(
                success=False,
                mod_id=mod_id,
                removed_files=[],
                reverted_files=[],
                errors=["Mod 未安装"],
            )

        mod = self._installed[mod_id]
        removed_files = list(mod.files)
        reverted_files = []
        errors = []

        # 1. 从加载顺序中移除
        self._load_order = [m for m in self._load_order if m != mod_id]

        # 2. 重新调整后续 Mod 的顺序
        for i, mid in enumerate(self._load_order):
            if mid in self._installed:
                self._installed[mid].install_order = i

        # 3. 移除记录
        del self._installed[mod_id]

        return UninstallResult(
            success=True,
            mod_id=mod_id,
            removed_files=removed_files,
            reverted_files=reverted_files,
            errors=errors,
        )

    async def enable_mod(self, mod_id: str) -> bool:
        """启用 Mod"""
        if mod_id not in self._installed:
            return False
        self._installed[mod_id].status = ModStatus.ACTIVE
        return True

    async def disable_mod(self, mod_id: str) -> bool:
        """禁用 Mod"""
        if mod_id not in self._installed:
            return False
        self._installed[mod_id].status = ModStatus.DISABLED
        return True

    async def create_mod_stack(self, mod_ids: list[str] | None = None) -> ModStack:
        """创建 Mod 堆栈"""
        if mod_ids is None:
            mod_ids = self._load_order

        # 拓扑排序（基于依赖关系）
        sorted_ids = self._topological_sort(mod_ids)

        # 收集 Mod
        mods = []
        conflicts = []
        for mid in sorted_ids:
            if mid in self._installed:
                mods.append(self._installed[mid])
                conflicts.extend(self._installed[mid].conflicts)

        # 检查有效性
        is_valid = not any(c.severity == "error" for c in conflicts)

        return ModStack(
            mods=mods,
            load_order=sorted_ids,
            conflicts=conflicts,
            is_valid=is_valid,
        )

    def _topological_sort(self, mod_ids: list[str]) -> list[str]:
        """拓扑排序"""
        # 构建依赖图
        graph = {mid: set() for mid in mod_ids}
        in_degree = dict.fromkeys(mod_ids, 0)

        for mid in mod_ids:
            if mid in self._installed:
                for dep in self._installed[mid].dependencies:
                    if dep in mod_ids:
                        graph[dep].add(mid)
                        in_degree[mid] += 1

        # Kahn 算法
        queue = [mid for mid in mod_ids if in_degree[mid] == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in graph.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 如果有剩余（循环依赖），按安装顺序追加
        for mid in mod_ids:
            if mid not in result:
                result.append(mid)

        return result

    def get_installed_mods(self) -> list[InstalledMod]:
        """获取所有已安装的 Mod"""
        return list(self._installed.values())

    def get_active_mods(self) -> list[InstalledMod]:
        """获取活跃的 Mod"""
        return [
            m
            for m in self._installed.values()
            if m.status in [ModStatus.INSTALLED, ModStatus.ACTIVE]
        ]

    def get_mod_conflicts(self, mod_id: str) -> list[ModConflict]:
        """获取 Mod 的冲突"""
        if mod_id not in self._installed:
            return []
        return self._installed[mod_id].conflicts

    def check_compatibility(self, mod_a: str, mod_b: str) -> list[ModConflict]:
        """检查两个 Mod 的兼容性"""
        conflicts = []

        if mod_a not in self._installed or mod_b not in self._installed:
            return conflicts

        a = self._installed[mod_a]
        b = self._installed[mod_b]

        # 文件冲突
        file_conflicts = set(a.files) & set(b.files)
        for f in file_conflicts:
            conflicts.append(
                ModConflict(
                    conflict_type="file_collision",
                    mod_a=mod_a,
                    mod_b=mod_b,
                    description=f"文件冲突: {f}",
                    file_path=f,
                )
            )

        return conflicts

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        status_counts = {}
        for mod in self._installed.values():
            name = mod.status.name
            status_counts[name] = status_counts.get(name, 0) + 1

        total_conflicts = sum(len(m.conflicts) for m in self._installed.values())

        return {
            "total_mods": len(self._installed),
            "status_breakdown": status_counts,
            "total_conflicts": total_conflicts,
            "load_order": self._load_order,
        }
