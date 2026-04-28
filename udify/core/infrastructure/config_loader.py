"""
Udify Config File Loader

从 YAML/JSON 文件加载配置。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from udify.core.infrastructure.config_center import ConfigCenter


class ConfigFileLoader:
    """
    配置文件加载器

    支持:
    - YAML (.yaml, .yml)
    - JSON (.json)
    - TOML (.toml)
    """

    def __init__(self, config: Optional[ConfigCenter] = None) -> None:
        self.config = config or ConfigCenter()

    def load(self, path: Path) -> ConfigCenter:
        """从文件加载配置"""
        suffix = path.suffix.lower()

        if suffix in (".yaml", ".yml"):
            return self._load_yaml(path)
        elif suffix == ".json":
            return self._load_json(path)
        elif suffix == ".toml":
            return self._load_toml(path)
        else:
            raise ValueError(f"Unsupported config format: {suffix}")

    def _load_json(self, path: Path) -> ConfigCenter:
        """加载 JSON 配置"""
        data = json.loads(path.read_text(encoding="utf-8"))
        self._apply_dict(data)
        return self.config

    def _load_yaml(self, path: Path) -> ConfigCenter:
        """加载 YAML 配置"""
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self._apply_dict(data)
        except ImportError:
            # 如果没有 PyYAML，尝试简单解析
            data = self._parse_simple_yaml(path.read_text(encoding="utf-8"))
            self._apply_dict(data)
        return self.config

    def _load_toml(self, path: Path) -> ConfigCenter:
        """加载 TOML 配置"""
        try:
            import tomllib
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            self._apply_dict(data)
        except ImportError:
            raise ImportError("tomllib is required for TOML support (Python 3.11+)")
        return self.config

    def _apply_dict(self, data: Dict[str, Any]) -> None:
        """将字典应用到配置"""
        for section, values in data.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    self.config.set(f"{section}.{key}", value)
            else:
                self.config.set(section, values)

    def _parse_simple_yaml(self, content: str) -> Dict[str, Any]:
        """简单 YAML 解析器（无需 PyYAML）"""
        result: Dict[str, Any] = {}
        current_section = None

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Section
            if not line.startswith(" ") and not line.startswith("\t") and stripped.endswith(":"):
                current_section = stripped[:-1]
                result[current_section] = {}
                continue

            # Key-value
            if ":" in stripped and current_section is not None:
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip()

                # 类型转换
                if value.isdigit():
                    value = int(value)
                elif value.replace(".", "").isdigit():
                    value = float(value)
                elif value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                elif (value.startswith('"') and value.endswith('"')) or \
                     (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                result[current_section][key] = value

        return result

    def save(self, path: Path) -> None:
        """保存配置到文件"""
        suffix = path.suffix.lower()
        data = self.config.to_dict()

        if suffix == ".json":
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        elif suffix in (".yaml", ".yml"):
            try:
                import yaml
                path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            except ImportError:
                raise ImportError("PyYAML is required for YAML output")
        else:
            raise ValueError(f"Unsupported output format: {suffix}")
