"""
Udify Backup Manager

自动备份游戏文件，支持快照、差异备份和恢复。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BackupSnapshot:
    """备份快照"""
    snapshot_id: str
    game_root: str
    created_at: datetime
    description: str
    file_count: int
    total_size: int
    file_hashes: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "game_root": self.game_root,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "file_hashes": self.file_hashes,
        }


class BackupManager:
    """
    备份管理器

    特性:
    - 完整快照备份
    - 差异备份（基于哈希）
    - 按会话关联备份
    - 一键恢复
    - 备份清理（保留策略）
    """

    def __init__(self, backup_dir: Path = Path(".udify/backups")) -> None:
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._snapshots: List[BackupSnapshot] = []
        self._load_index()

    def create_snapshot(
        self,
        game_root: Path,
        description: str = "",
        session_id: Optional[str] = None,
    ) -> BackupSnapshot:
        """
        创建完整快照备份
        """
        snapshot_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = self.backup_dir / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        file_hashes: Dict[str, str] = {}
        file_count = 0
        total_size = 0

        # 遍历游戏目录
        for file_path in game_root.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(game_root))
                backup_path = snapshot_dir / rel_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)

                # 复制文件
                shutil.copy2(file_path, backup_path)

                # 计算哈希
                file_hash = self._hash_file(file_path)
                file_hashes[rel_path] = file_hash

                file_count += 1
                total_size += file_path.stat().st_size

        snapshot = BackupSnapshot(
            snapshot_id=snapshot_id,
            game_root=str(game_root),
            created_at=datetime.now(),
            description=description,
            file_count=file_count,
            total_size=total_size,
            file_hashes=file_hashes,
        )

        self._snapshots.append(snapshot)
        self._save_index()

        return snapshot

    def restore_snapshot(self, snapshot_id: str, game_root: Path) -> Dict[str, Any]:
        """
        从快照恢复

        Returns:
            恢复结果统计
        """
        snapshot_dir = self.backup_dir / snapshot_id
        if not snapshot_dir.exists():
            return {"success": False, "error": f"Snapshot {snapshot_id} not found"}

        restored = 0
        failed = 0

        for backup_file in snapshot_dir.rglob("*"):
            if backup_file.is_file():
                rel_path = str(backup_file.relative_to(snapshot_dir))
                target_path = game_root / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)

                try:
                    shutil.copy2(backup_file, target_path)
                    restored += 1
                except Exception:
                    failed += 1

        return {
            "success": True,
            "restored": restored,
            "failed": failed,
            "snapshot_id": snapshot_id,
        }

    def create_delta_backup(
        self,
        game_root: Path,
        base_snapshot_id: str,
        session_id: Optional[str] = None,
    ) -> Optional[BackupSnapshot]:
        """
        基于基础快照创建差异备份
        """
        base_snapshot = self.get_snapshot(base_snapshot_id)
        if not base_snapshot:
            return None

        delta_id = session_id or f"delta_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        delta_dir = self.backup_dir / delta_id
        delta_dir.mkdir(parents=True, exist_ok=True)

        file_hashes: Dict[str, str] = {}
        file_count = 0
        total_size = 0

        for file_path in game_root.rglob("*"):
            if not file_path.is_file():
                continue

            rel_path = str(file_path.relative_to(game_root))
            current_hash = self._hash_file(file_path)

            # 检查是否与基础快照不同
            base_hash = base_snapshot.file_hashes.get(rel_path)
            if base_hash != current_hash:
                # 文件有变化，备份
                backup_path = delta_dir / rel_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, backup_path)

                file_hashes[rel_path] = current_hash
                file_count += 1
                total_size += file_path.stat().st_size

        snapshot = BackupSnapshot(
            snapshot_id=delta_id,
            game_root=str(game_root),
            created_at=datetime.now(),
            description=f"Delta from {base_snapshot_id}",
            file_count=file_count,
            total_size=total_size,
            file_hashes=file_hashes,
        )

        self._snapshots.append(snapshot)
        self._save_index()

        return snapshot

    def get_snapshot(self, snapshot_id: str) -> Optional[BackupSnapshot]:
        """获取快照"""
        for s in self._snapshots:
            if s.snapshot_id == snapshot_id:
                return s
        return None

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """列出所有快照"""
        return [s.to_dict() for s in self._snapshots]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照"""
        snapshot_dir = self.backup_dir / snapshot_id
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)

        self._snapshots = [s for s in self._snapshots if s.snapshot_id != snapshot_id]
        self._save_index()
        return True

    def cleanup_old_snapshots(self, keep_count: int = 10) -> int:
        """清理旧快照，保留最近 N 个"""
        if len(self._snapshots) <= keep_count:
            return 0

        # 按时间排序，保留最新的
        sorted_snapshots = sorted(
            self._snapshots,
            key=lambda s: s.created_at,
            reverse=True,
        )

        to_delete = sorted_snapshots[keep_count:]
        for snapshot in to_delete:
            self.delete_snapshot(snapshot.snapshot_id)

        return len(to_delete)

    def _hash_file(self, file_path: Path) -> str:
        """计算文件哈希"""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _save_index(self) -> None:
        """保存索引"""
        index_path = self.backup_dir / "index.json"
        data = [s.to_dict() for s in self._snapshots]
        index_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _load_index(self) -> None:
        """加载索引"""
        index_path = self.backup_dir / "index.json"
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                for item in data:
                    self._snapshots.append(BackupSnapshot(
                        snapshot_id=item["snapshot_id"],
                        game_root=item["game_root"],
                        created_at=datetime.fromisoformat(item["created_at"]),
                        description=item.get("description", ""),
                        file_count=item.get("file_count", 0),
                        total_size=item.get("total_size", 0),
                        file_hashes=item.get("file_hashes", {}),
                    ))
            except Exception:
                pass
