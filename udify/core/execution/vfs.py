"""
Udify Execution - Virtual File System (VFS)

虚拟文件系统：预览模式，在内存中模拟文件修改，不影响实际文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class VFSNode:
    """VFS 节点"""

    path: str
    content: str | None = None
    binary_content: bytes | None = None
    is_modified: bool = False
    is_deleted: bool = False
    is_new: bool = False

    def get_content(self) -> str | None:
        return self.content

    def set_content(self, content: str) -> None:
        self.content = content
        self.is_modified = True

    def get_binary(self) -> bytes | None:
        return self.binary_content

    def set_binary(self, content: bytes) -> None:
        self.binary_content = content
        self.is_modified = True


class VirtualFileSystem:
    """
    虚拟文件系统

    特性:
    - 内存中模拟文件系统
    - 支持文本和二进制文件
    - 追踪修改状态
    - 支持 diff 输出
    - 支持应用到实际文件系统
    """

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self._files: dict[str, VFSNode] = {}
        self._originals: dict[str, str] = {}  # 原始内容备份

    def read_file(self, path: str) -> str | None:
        """读取文件（优先从 VFS，否则从实际文件系统）"""
        # 1. 检查 VFS
        if path in self._files:
            node = self._files[path]
            if node.is_deleted:
                return None
            return node.get_content()

        # 2. 从实际文件系统读取
        full_path = self.base_path / path
        if full_path.exists():
            content = full_path.read_text(encoding="utf-8")
            # 缓存到 VFS
            self._files[path] = VFSNode(path=path, content=content)
            self._originals[path] = content
            return content

        return None

    def write_file(self, path: str, content: str) -> None:
        """写入文件（仅 VFS）"""
        # 备份原始内容
        if path not in self._originals:
            original = self.read_file(path)
            if original is not None:
                self._originals[path] = original

        if path in self._files:
            self._files[path].set_content(content)
        else:
            self._files[path] = VFSNode(
                path=path,
                content=content,
                is_new=True,
            )

    def delete_file(self, path: str) -> bool:
        """删除文件（仅 VFS）"""
        if path in self._files:
            self._files[path].is_deleted = True
            return True

        # 检查实际文件是否存在
        full_path = self.base_path / path
        if full_path.exists():
            # 读取原始内容备份
            self._originals[path] = full_path.read_text(encoding="utf-8")
            self._files[path] = VFSNode(path=path, is_deleted=True)
            return True

        return False

    def get_diff(self, path: str) -> dict[str, Any] | None:
        """获取文件的 diff"""
        if path not in self._files:
            return None

        node = self._files[path]
        original = self._originals.get(path, "")
        current = node.get_content() or ""

        if node.is_deleted:
            return {
                "path": path,
                "status": "deleted",
                "original": original,
                "current": None,
            }

        if node.is_new:
            return {
                "path": path,
                "status": "new",
                "original": None,
                "current": current,
            }

        if original != current:
            return {
                "path": path,
                "status": "modified",
                "original": original,
                "current": current,
                "diff": self._compute_diff(original, current),
            }

        return None

    def get_all_diffs(self) -> list[dict[str, Any]]:
        """获取所有修改的 diff"""
        diffs = []
        for path in self._files:
            diff = self.get_diff(path)
            if diff:
                diffs.append(diff)
        return diffs

    def _compute_diff(self, original: str, current: str) -> list[dict[str, Any]]:
        """计算文本差异"""
        import difflib

        original_lines = original.splitlines(keepends=True)
        current_lines = current.splitlines(keepends=True)

        diff = list(
            difflib.unified_diff(
                original_lines,
                current_lines,
                fromfile="original",
                tofile="modified",
                lineterm="",
            )
        )

        # 解析统一差异格式
        changes = []
        for line in diff[2:]:  # 跳过文件头
            if line.startswith("+") and not line.startswith("+++"):
                changes.append({"type": "add", "line": line[1:]})
            elif line.startswith("-") and not line.startswith("---"):
                changes.append({"type": "remove", "line": line[1:]})

        return changes

    def apply_to_filesystem(self) -> dict[str, Any]:
        """将 VFS 中的修改应用到实际文件系统"""
        results = {
            "applied": [],
            "failed": [],
        }

        for path, node in self._files.items():
            full_path = self.base_path / path

            try:
                if node.is_deleted:
                    if full_path.exists():
                        full_path.unlink()
                    results["applied"].append({"path": path, "action": "deleted"})
                elif node.is_new or node.is_modified:
                    # 确保目录存在
                    full_path.parent.mkdir(parents=True, exist_ok=True)

                    content = node.get_content()
                    if content is not None:
                        full_path.write_text(content, encoding="utf-8")
                    else:
                        binary = node.get_binary()
                        if binary is not None:
                            full_path.write_bytes(binary)

                    action = "created" if node.is_new else "modified"
                    results["applied"].append({"path": path, "action": action})

            except Exception as e:
                results["failed"].append({"path": path, "error": str(e)})

        return results

    def rollback(self) -> None:
        """回滚所有修改（清空 VFS）"""
        self._files.clear()
        self._originals.clear()

    def get_modified_files(self) -> list[str]:
        """获取所有被修改的文件路径"""
        return [
            path
            for path, node in self._files.items()
            if node.is_modified or node.is_deleted or node.is_new
        ]

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        modified = sum(1 for n in self._files.values() if n.is_modified)
        deleted = sum(1 for n in self._files.values() if n.is_deleted)
        new = sum(1 for n in self._files.values() if n.is_new)

        return {
            "total_files": len(self._files),
            "modified": modified,
            "deleted": deleted,
            "new": new,
            "base_path": str(self.base_path),
        }
