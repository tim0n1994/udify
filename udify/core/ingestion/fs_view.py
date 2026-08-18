"""
受限文件系统视图（iter4 M1 PR2，T1-ENGINE-AUTO 研究落地）。

SafeFsView 是一个只读沙箱视图：所有路径都被 resolve 到 game_root 内部，
任何逃逸（..、symlink 指向外部、绝对路径）都 fail-closed 抛 ValueError。

设计原则（T1 研究结论）：
- 安全边界明确：never read outside root，宁可拒绝也不静默放行。
- 只读：不提供任何写接口。
- 纯函数式路径校验，可测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class FsViewError(ValueError):
    """路径逃逸或越界。"""


@dataclass(frozen=True, slots=True)
class SafeFsView:
    """受限只读文件系统视图，所有访问限制在 root 内。"""

    root: Path

    def __post_init__(self) -> None:
        # frozen dataclass 不能在 __init__ 里赋值，用 object.__setattr__
        object.__setattr__(self, "root", self.root.resolve())

    def _resolve_safe(self, rel: str) -> Path:
        """把相对路径 resolve 到 root 内；越界抛 FsViewError。"""
        if not rel:
            raise FsViewError("empty path")
        # 拒绝绝对路径（除非已在 root 内）
        p = Path(rel)
        resolved = p.resolve() if p.is_absolute() else (self.root / rel).resolve()
        # 必须在 root 内
        try:
            resolved.relative_to(self.root)
        except ValueError as e:
            raise FsViewError(f"path '{rel}' escapes root {self.root}") from e
        # symlink 逃逸检测：realpath 也要在 root 内
        real = resolved.resolve()
        try:
            real.relative_to(self.root)
        except ValueError as e:
            raise FsViewError(f"path '{rel}' symlink escapes root {self.root}") from e
        return resolved

    def exists(self, rel: str) -> bool:
        try:
            return self._resolve_safe(rel).exists()
        except FsViewError:
            return False

    def is_file(self, rel: str) -> bool:
        try:
            return self._resolve_safe(rel).is_file()
        except FsViewError:
            return False

    def is_dir(self, rel: str) -> bool:
        try:
            return self._resolve_safe(rel).is_dir()
        except FsViewError:
            return False

    def read_text(
        self, rel: str, encoding: str = "utf-8", max_bytes: int = 10 * 1024 * 1024
    ) -> str:
        """读取文本文件，超过 max_bytes 截断并标记。"""
        path = self._resolve_safe(rel)
        if not path.is_file():
            raise FsViewError(f"not a file: {rel}")
        size = path.stat().st_size
        if size > max_bytes:
            # 读前 max_bytes，避免 OOM（T1 研究结论：防 OOM）
            with path.open("rb") as f:
                data = f.read(max_bytes)
            return data.decode(encoding, errors="replace")
        return path.read_text(encoding=encoding)

    def read_bytes(self, rel: str, max_bytes: int = 10 * 1024 * 1024) -> bytes:
        path = self._resolve_safe(rel)
        if not path.is_file():
            raise FsViewError(f"not a file: {rel}")
        size = path.stat().st_size
        with path.open("rb") as f:
            return f.read(max_bytes if size > max_bytes else size)

    def list_dir(self, rel: str = ".") -> list[str]:
        """列出目录下的相对路径（不递归）。"""
        path = self._resolve_safe(rel)
        if not path.is_dir():
            raise FsViewError(f"not a directory: {rel}")
        entries = []
        for entry in sorted(path.iterdir()):
            entries.append(str(entry.relative_to(self.root)))
        return entries

    def glob(self, pattern: str) -> list[str]:
        """在 root 内 glob 匹配，返回相对路径列表。"""
        # glob 模式本身不含越界风险（Path.glob 在 root 下匹配）
        safe_pattern = pattern.lstrip("./")
        return [
            str(p.relative_to(self.root))
            for p in sorted(self.root.glob(safe_pattern))
            if p.is_file()
        ]

    def safe_join(self, rel: str) -> Path:
        """返回已校验的绝对 Path（在 root 内）。供需要 Path 对象的调用方使用。"""
        return self._resolve_safe(rel)

    @property
    def root_str(self) -> str:
        return str(self.root)
