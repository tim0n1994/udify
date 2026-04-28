"""
Udify Infrastructure - Cache Manager

分层缓存系统：L1 内存 + L2 磁盘 + L3 Redis
"""

from __future__ import annotations

import json
import os
import pickle
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generic, Optional, TypeVar

from udify.core.infrastructure.config_center import config


T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """缓存条目"""
    key: str
    value: T
    created_at: datetime
    ttl_seconds: int
    hit_count: int = 0

    def is_expired(self) -> bool:
        elapsed = (datetime.now().replace(tzinfo=None) - self.created_at).total_seconds()
        return elapsed > self.ttl_seconds


class LRUCache(Generic[T]):
    """L1: 内存 LRU 缓存"""

    def __init__(self, maxsize: int = 1000):
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> Optional[T]:
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if entry.is_expired():
            del self._cache[key]
            return None

        entry.hit_count += 1
        self._cache.move_to_end(key)
        return entry.value

    def set(self, key: str, value: T, ttl_seconds: int = 3600) -> None:
        if key in self._cache:
            del self._cache[key]

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=datetime.now().replace(tzinfo=None),
            ttl_seconds=ttl_seconds,
        )
        self._cache[key] = entry
        self._cache.move_to_end(key)

        # 淘汰最久未使用
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        self._cache.clear()

    def keys(self) -> list:
        return list(self._cache.keys())


class DiskCache:
    """L2: 磁盘缓存"""

    def __init__(self, directory: str = ".udify/cache", max_size_bytes: int = int(1e9)):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_size = max_size_bytes
        self._meta_file = self._dir / "cache_meta.json"
        self._meta: Dict[str, Dict[str, Any]] = self._load_meta()

    def _load_meta(self) -> Dict[str, Any]:
        if self._meta_file.exists():
            with open(self._meta_file, "r") as f:
                return json.load(f)
        return {}

    def _save_meta(self) -> None:
        with open(self._meta_file, "w") as f:
            json.dump(self._meta, f)

    def _get_path(self, key: str) -> Path:
        # 使用哈希作为文件名，避免非法字符
        safe_key = hash(key) % 1000000
        return self._dir / f"cache_{safe_key}.pickle"

    async def get(self, key: str) -> Optional[Any]:
        if key not in self._meta:
            return None

        meta = self._meta[key]
        created = datetime.fromisoformat(meta["created_at"])
        elapsed = (datetime.now().replace(tzinfo=None) - created).total_seconds()

        if elapsed > meta["ttl_seconds"]:
            await self.delete(key)
            return None

        path = self._get_path(key)
        if not path.exists():
            return None

        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        path = self._get_path(key)

        with open(path, "wb") as f:
            pickle.dump(value, f)

        self._meta[key] = {
            "created_at": datetime.now().replace(tzinfo=None).isoformat(),
            "ttl_seconds": ttl_seconds,
            "size": path.stat().st_size,
        }

        self._save_meta()
        await self._cleanup_if_needed()

    async def delete(self, key: str) -> bool:
        if key not in self._meta:
            return False

        path = self._get_path(key)
        if path.exists():
            path.unlink()

        del self._meta[key]
        self._save_meta()
        return True

    async def contains(self, key: str) -> bool:
        if key not in self._meta:
            return False
        meta = self._meta[key]
        created = datetime.fromisoformat(meta["created_at"])
        elapsed = (datetime.now().replace(tzinfo=None) - created).total_seconds()
        return elapsed <= meta["ttl_seconds"]

    async def _cleanup_if_needed(self) -> None:
        """清理过期或超容的缓存"""
        total_size = sum(m["size"] for m in self._meta.values())

        if total_size <= self._max_size:
            return

        # 按时间排序，删除最旧的
        items = sorted(
            self._meta.items(),
            key=lambda x: x[1]["created_at"],
        )

        for key, meta in items:
            if total_size <= self._max_size * 0.8:
                break
            await self.delete(key)
            total_size -= meta["size"]


class CacheManager:
    """
    缓存管理器

    L1: 内存 LRU
    L2: 磁盘
    L3: Redis（占位，需要时实现）
    """

    def __init__(self) -> None:
        self.l1 = LRUCache(maxsize=config.cache.l1_max_size)
        self.l2 = DiskCache(
            directory=config.cache.l2_directory,
            max_size_bytes=config.cache.l2_max_size_bytes,
        )

    async def get(self, key: str) -> Optional[Any]:
        """三级缓存读取"""
        # L1
        value = self.l1.get(key)
        if value is not None:
            return value

        # L2
        value = await self.l2.get(key)
        if value is not None:
            self.l1.set(key, value, ttl_seconds=config.cache.l2_ttl_seconds)
            return value

        return None

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """三级缓存写入"""
        if ttl_seconds is None:
            ttl_seconds = config.cache.l2_ttl_seconds

        self.l1.set(key, value, ttl_seconds=ttl_seconds)
        await self.l2.set(key, value, ttl_seconds=ttl_seconds)

    async def invalidate(self, key: str) -> None:
        """失效指定缓存"""
        self.l1.delete(key)
        await self.l2.delete(key)

    async def invalidate_pattern(self, pattern: str) -> int:
        """按模式失效缓存"""
        count = 0
        for key in self.l1.keys():
            if pattern in key:
                self.l1.delete(key)
                count += 1

        # L2 扫描较慢，暂不实现模式匹配
        return count
