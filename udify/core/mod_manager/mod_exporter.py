"""
Udify Mod Exporter

将 Mod 打包为可分发格式（ZIP / 目录结构）。
支持生成 Mod 元数据、依赖声明、版本信息。
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from udify.models.cdl_patch import CDLPatch


@dataclass
class ModManifest:
    """Mod 清单"""
    mod_id: str
    name: str
    version: str
    author: str
    description: str = ""
    game_id: str = ""
    game_version: str = ""
    dependencies: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    operations_count: int = 0
    files_modified: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_version": "1.0",
            "mod_id": self.mod_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "game_id": self.game_id,
            "game_version": self.game_version,
            "dependencies": self.dependencies,
            "conflicts": self.conflicts,
            "tags": self.tags,
            "created_at": self.created_at,
            "operations_count": self.operations_count,
            "files_modified": self.files_modified,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModManifest":
        return cls(
            mod_id=data["mod_id"],
            name=data["name"],
            version=data["version"],
            author=data["author"],
            description=data.get("description", ""),
            game_id=data.get("game_id", ""),
            game_version=data.get("game_version", ""),
            dependencies=data.get("dependencies", []),
            conflicts=data.get("conflicts", []),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            operations_count=data.get("operations_count", 0),
            files_modified=data.get("files_modified", []),
        )


class ModExporter:
    """
    Mod 导出器

    支持:
    - ZIP 打包
    - 目录导出
    - 元数据生成
    - 补丁序列化
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_zip(
        self,
        patch: CDLPatch,
        manifest: ModManifest,
        mod_files: Optional[Dict[str, str]] = None,
    ) -> Path:
        """
        导出为 ZIP 格式

        Returns:
            生成的 ZIP 文件路径
        """
        filename = f"{manifest.mod_id}_v{manifest.version}.zip"
        output_path = self.output_dir / filename

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 写入清单
            zf.writestr("manifest.json", json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False))

            # 写入补丁
            zf.writestr("patch.json", json.dumps(patch.to_dict(), indent=2, default=str))

            # 写入修改后的文件
            if mod_files:
                for file_path, content in mod_files.items():
                    zf.writestr(f"files/{file_path}", content)

            # 写入 README
            readme = self._generate_readme(manifest)
            zf.writestr("README.md", readme)

        return output_path

    def export_directory(
        self,
        patch: CDLPatch,
        manifest: ModManifest,
        mod_files: Optional[Dict[str, str]] = None,
    ) -> Path:
        """
        导出为目录结构

        Returns:
            生成的目录路径
        """
        mod_dir = self.output_dir / f"{manifest.mod_id}_v{manifest.version}"
        mod_dir.mkdir(parents=True, exist_ok=True)

        # 清单
        (mod_dir / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 补丁
        (mod_dir / "patch.json").write_text(
            json.dumps(patch.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        # 修改后的文件
        if mod_files:
            files_dir = mod_dir / "files"
            files_dir.mkdir(exist_ok=True)
            for file_path, content in mod_files.items():
                target = files_dir / file_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

        # README
        (mod_dir / "README.md").write_text(
            self._generate_readme(manifest),
            encoding="utf-8",
        )

        return mod_dir

    def import_zip(self, zip_path: Path) -> tuple[ModManifest, CDLPatch]:
        """从 ZIP 导入 Mod"""
        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest_data = json.loads(zf.read("manifest.json"))
            patch_data = json.loads(zf.read("patch.json"))

        manifest = ModManifest.from_dict(manifest_data)
        patch = CDLPatch.from_dict(patch_data)

        return manifest, patch

    def _generate_readme(self, manifest: ModManifest) -> str:
        """生成 README"""
        lines = [
            f"# {manifest.name}",
            "",
            f"**作者**: {manifest.author}",
            f"**版本**: {manifest.version}",
            f"**游戏**: {manifest.game_id} ({manifest.game_version})",
            f"**创建时间**: {manifest.created_at}",
            "",
            "## 描述",
            manifest.description or "暂无描述",
            "",
            "## 修改文件",
        ]
        for f in manifest.files_modified:
            lines.append(f"- {f}")

        if manifest.dependencies:
            lines.extend(["", "## 依赖"])
            for dep in manifest.dependencies:
                lines.append(f"- {dep}")

        if manifest.tags:
            lines.extend(["", "## 标签"])
            lines.append(", ".join(manifest.tags))

        return "\n".join(lines)

    def list_exported_mods(self) -> List[Dict[str, Any]]:
        """列出所有已导出的 Mod"""
        mods = []
        for path in self.output_dir.iterdir():
            if path.suffix == ".zip":
                try:
                    with zipfile.ZipFile(path, "r") as zf:
                        manifest = json.loads(zf.read("manifest.json"))
                        mods.append({
                            "path": str(path),
                            **manifest,
                        })
                except Exception:
                    continue
            elif path.is_dir() and (path / "manifest.json").exists():
                try:
                    manifest = json.loads((path / "manifest.json").read_text())
                    mods.append({
                        "path": str(path),
                        **manifest,
                    })
                except Exception:
                    continue
        return mods
