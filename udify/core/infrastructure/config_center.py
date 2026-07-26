"""
Udify Infrastructure - Configuration Center

集中配置管理，支持环境变量、配置文件、动态更新。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCTSConfig:
    """MCTS 配置"""

    num_iterations: int = 100
    exploration_constant: float = 1.414
    max_depth: int = 10
    enable_rollout: bool = True
    rollout_steps: int = 5
    early_termination_threshold: float = 0.9
    expand_threshold: int = 1


@dataclass
class CostConfig:
    """成本配置"""

    budget_per_session: float = 0.5  # 美元
    llm_timeout_seconds: float = 30.0
    planning_timeout_seconds: float = 10.0
    perception_timeout_seconds: float = 2.0
    execution_timeout_seconds: float = 5.0
    validation_timeout_seconds: float = 30.0


@dataclass
class CacheConfig:
    """缓存配置"""

    l1_max_size: int = 1000
    l2_directory: str = ".udify/cache"
    l2_max_size_bytes: int = int(1e9)
    l2_ttl_seconds: int = 3600
    l3_host: str = "localhost"
    l3_port: int = 6379
    l3_ttl_seconds: int = 86400


@dataclass
class SecurityConfig:
    """安全配置"""

    max_input_length: int = 1000
    forbidden_keywords: list[str] = field(default_factory=list)
    sandbox_memory_limit: str = "512m"
    sandbox_cpu_limit: float = 1.0
    sandbox_timeout_seconds: int = 10
    enable_network_isolation: bool = True


@dataclass
class GameModConfig:
    """游戏魔改特化配置"""

    max_mod_operations: int = 50
    max_numeric_scale: float = 10.0
    min_numeric_scale: float = 0.1
    preservative_bias: float = 0.7
    enable_preview_mode: bool = True
    enable_auto_rollback: bool = True
    supported_formats: list[str] = field(
        default_factory=lambda: [
            ".ini",
            ".obj",
            ".txt",
            ".npc",
            ".lua",
            ".asf",
            ".msf",
            ".mpc",
            ".map",
            ".mmf",
            ".shd",
            ".xnb",
        ]
    )


class ConfigCenter:
    """
    配置中心

    优先级: 环境变量 > 配置文件 > 默认值
    """

    def __init__(self) -> None:
        self.mcts = MCTSConfig()
        self.cost = CostConfig()
        self.cache = CacheConfig()
        self.security = SecurityConfig(
            forbidden_keywords=["rm -rf", "drop table", "delete from", "format c:"],
        )
        self.game_mod = GameModConfig()
        self._overrides: dict[str, Any] = {}

    def load_from_env(self) -> None:
        """从环境变量加载配置"""
        # MCTS
        if os.getenv("UDIFY_MCTS_ITERATIONS"):
            self.mcts.num_iterations = int(os.getenv("UDIFY_MCTS_ITERATIONS"))
        if os.getenv("UDIFY_MCTS_MAX_DEPTH"):
            self.mcts.max_depth = int(os.getenv("UDIFY_MCTS_MAX_DEPTH"))

        # Cost
        if os.getenv("UDIFY_COST_BUDGET"):
            self.cost.budget_per_session = float(os.getenv("UDIFY_COST_BUDGET"))

        # Cache
        if os.getenv("UDIFY_CACHE_L2_DIR"):
            self.cache.l2_directory = os.getenv("UDIFY_CACHE_L2_DIR")

        # Security
        if os.getenv("UDIFY_SANDBOX_MEMORY"):
            self.security.sandbox_memory_limit = os.getenv("UDIFY_SANDBOX_MEMORY")

        # Game Mod
        if os.getenv("UDIFY_MAX_OPERATIONS"):
            self.game_mod.max_mod_operations = int(os.getenv("UDIFY_MAX_OPERATIONS"))

    def set(self, key: str, value: Any) -> None:
        """动态设置配置"""
        self._overrides[key] = value
        # 更新对应的数据类
        parts = key.split(".")
        if len(parts) == 2:
            section, attr = parts
            section_obj = getattr(self, section, None)
            if section_obj and hasattr(section_obj, attr):
                setattr(section_obj, attr, value)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        if key in self._overrides:
            return self._overrides[key]

        parts = key.split(".")
        if len(parts) == 2:
            section, attr = parts
            section_obj = getattr(self, section, None)
            if section_obj and hasattr(section_obj, attr):
                return getattr(section_obj, attr)

        return default

    def to_dict(self) -> dict[str, Any]:
        """导出为字典"""
        return {
            "mcts": self.mcts.__dict__,
            "cost": self.cost.__dict__,
            "cache": self.cache.__dict__,
            "security": self.security.__dict__,
            "game_mod": self.game_mod.__dict__,
            "overrides": self._overrides,
        }


# 全局配置实例
config = ConfigCenter()
config.load_from_env()
