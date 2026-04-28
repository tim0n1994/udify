"""
Udify Security - Input Sanitizer

输入消毒层：防止 Prompt Injection、恶意输入、超出范围的请求。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from udify.core.infrastructure.config_center import config


@dataclass
class SanitizationResult:
    """消毒结果"""
    is_valid: bool
    sanitized_input: str
    original_input: str
    violations: List[str]
    risk_level: str = "low"  # low, medium, high, critical


class InputSanitizer:
    """
    输入消毒器

    检查维度:
    1. 长度限制
    2. 敏感词过滤
    3. Prompt Injection 检测
    4. 意图范围验证（拒绝非游戏魔改请求）
    5. 编码检测（防止 Unicode 欺骗）
    """

    # Prompt Injection 检测模式
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"forget\s+(all\s+)?(your\s+)?instructions",
        r"you\s+are\s+now\s+",
        r"system\s*:\s*",
        r"assistant\s*:\s*",
        r"user\s*:\s*",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"\{\{.*\}\}",  # Jinja2 模板注入
        r"\[%.*%\]",      # 模板注入
    ]

    # 允许的意图关键词（游戏魔改相关）
    ALLOWED_INTENT_KEYWORDS = [
        "游戏", "game", "mod", "魔改", "修改", "change", "增加", "add",
        "删除", "delete", "移除", "remove", "调整", "adjust", "平衡",
        "balance", "难度", "difficulty", "血量", "hp", "生命", "life",
        "经验", "exp", "掉落", "drop", "loot", "技能", "skill", "魔法",
        "magic", "npc", "角色", "character", "物品", "item", "武器",
        "weapon", "护甲", "armor", "任务", "quest", "剧情", "story",
        "对话", "dialog", "地图", "map", "场景", "scene", "商店",
        "shop", "价格", "price", "金币", "gold", "属性", "stat",
    ]

    def __init__(self) -> None:
        self.max_length = config.security.max_input_length
        self.forbidden_keywords = config.security.forbidden_keywords
        self.injection_patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

    def sanitize(self, user_input: str) -> SanitizationResult:
        """
        消毒用户输入

        Returns:
            SanitizationResult: 包含是否通过、消毒后输入、违规列表
        """
        violations = []
        risk_level = "low"
        original = user_input
        sanitized = user_input

        # 1. 长度检查
        if len(user_input) > self.max_length:
            violations.append(f"输入过长 ({len(user_input)} > {self.max_length})")
            sanitized = user_input[:self.max_length]
            risk_level = "medium"

        # 2. 禁止关键词检查
        for keyword in self.forbidden_keywords:
            if keyword.lower() in user_input.lower():
                violations.append(f"包含禁止关键词: {keyword}")
                risk_level = "critical"
                sanitized = sanitized.replace(keyword, "[FILTERED]")

        # 3. Prompt Injection 检测
        for pattern in self.injection_patterns:
            if pattern.search(user_input):
                violations.append(f"检测到 Prompt Injection 模式: {pattern.pattern}")
                risk_level = "critical"
                # 删除匹配部分
                sanitized = pattern.sub("[INJECTION_BLOCKED]", sanitized)

        # 4. 意图范围验证
        if not self._is_valid_intent(user_input):
            violations.append("请求超出游戏魔改范围")
            risk_level = "high"

        # 5. Unicode 欺骗检测
        normalized = self._normalize_unicode(user_input)
        if normalized != user_input:
            violations.append("检测到 Unicode 规范化差异（可能的欺骗攻击）")
            risk_level = "high"
            sanitized = normalized

        # 6. 控制字符检测
        control_chars = self._detect_control_chars(user_input)
        if control_chars:
            violations.append(f"检测到控制字符: {control_chars}")
            risk_level = "high"
            sanitized = self._remove_control_chars(sanitized)

        is_valid = len(violations) == 0 or risk_level not in ["high", "critical"]

        return SanitizationResult(
            is_valid=is_valid,
            sanitized_input=sanitized.strip(),
            original_input=original,
            violations=violations,
            risk_level=risk_level,
        )

    def _is_valid_intent(self, user_input: str) -> bool:
        """检查意图是否在游戏魔改范围内"""
        input_lower = user_input.lower()

        # 检查是否包含至少一个允许的关键词
        has_game_keyword = any(
            keyword.lower() in input_lower
            for keyword in self.ALLOWED_INTENT_KEYWORDS
        )

        if has_game_keyword:
            return True

        # 允许一些通用修改词（但必须有上下文）
        generic_modifiers = ["增加", "减少", "修改", "调整", "改变", "翻倍", "减半"]
        has_modifier = any(m in user_input for m in generic_modifiers)

        # 如果只有通用词没有游戏词，需要更严格的检查
        if has_modifier and not has_game_keyword:
            # 检查是否可能是游戏相关的（通过常见游戏术语）
            game_terms = ["boss", "enemy", "player", "level", "hp", "mp", "exp"]
            return any(t in input_lower for t in game_terms)

        return has_game_keyword

    def _normalize_unicode(self, text: str) -> str:
        """Unicode 规范化"""
        import unicodedata
        return unicodedata.normalize("NFKC", text)

    def _detect_control_chars(self, text: str) -> List[str]:
        """检测控制字符"""
        control_chars = []
        for i, char in enumerate(text):
            code = ord(char)
            if code < 32 and code not in [9, 10, 13]:  # 排除 tab, newline, carriage return
                control_chars.append(f"U+{code:04X}@{i}")
            elif code == 0x200E or code == 0x200F:  # LRM, RLM
                control_chars.append(f"U+{code:04X}@{i}")
            elif 0x202A <= code <= 0x202E:  # BiDi 控制字符
                control_chars.append(f"U+{code:04X}@{i}")
        return control_chars

    def _remove_control_chars(self, text: str) -> str:
        """移除控制字符"""
        result = []
        for char in text:
            code = ord(char)
            if code < 32 and code not in [9, 10, 13]:
                continue
            if code in [0x200E, 0x200F] or (0x202A <= code <= 0x202E):
                continue
            result.append(char)
        return "".join(result)


class OutputValidator:
    """
    输出验证器

    验证 AI 生成的输出是否符合预期格式，防止无效或恶意内容。
    """

    def __init__(self) -> None:
        self.max_script_length = 10000
        self.max_operations = config.game_mod.max_mod_operations

    def validate_patch(self, patch_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """验证 Patch 字典的合法性"""
        errors = []

        # 1. 检查操作数量
        operations = patch_dict.get("operations", [])
        if len(operations) > self.max_operations:
            errors.append(f"操作数量过多 ({len(operations)} > {self.max_operations})")

        # 2. 检查每个操作
        for i, op in enumerate(operations):
            op_errors = self._validate_operation(op, i)
            errors.extend(op_errors)

        # 3. 检查脚本内容
        for op in operations:
            if op.get("op_type") in ["INSERT_SCRIPT", "MODIFY_SCRIPT"]:
                code = op.get("payload", {}).get("code", "")
                script_errors = self._validate_script(code)
                errors.extend(script_errors)

        # 4. 检查数值范围
        for op in operations:
            if op.get("op_type") == "MODIFY_INI":
                key = op.get("payload", {}).get("key", "")
                value = op.get("payload", {}).get("new_value")
                if isinstance(value, (int, float)):
                    if value < 0 and key in ["MaxLife", "MaxMana", "Strength", "Dexterity"]:
                        errors.append(f"属性 {key} 不能为负数: {value}")
                    if abs(value) > 999999 and key in ["MaxLife", "MaxMana"]:
                        errors.append(f"属性 {key} 数值过大: {value}")

        return len(errors) == 0, errors

    def _validate_operation(self, op: Dict[str, Any], index: int) -> List[str]:
        """验证单个操作"""
        errors = []

        if "op_type" not in op:
            errors.append(f"操作 {index}: 缺少 op_type")
            return errors

        op_type = op["op_type"]
        valid_types = ["MODIFY_INI", "INSERT_SCRIPT", "REPLACE_ASSET", "EDIT_MAP", "ADD_RECORD", "MODIFY_PROPERTY", "ADD_NODE", "REMOVE_NODE", "ADD_EDGE", "REMOVE_EDGE", "ADD_ASSET", "REMOVE_ASSET"]

        if op_type not in valid_types:
            errors.append(f"操作 {index}: 未知操作类型 {op_type}")

        if "target_id" not in op:
            errors.append(f"操作 {index}: 缺少 target_id")

        return errors

    def _validate_script(self, code: str) -> List[str]:
        """验证脚本代码"""
        errors = []

        if len(code) > self.max_script_length:
            errors.append(f"脚本过长 ({len(code)} > {self.max_script_length})")

        # 检查危险模式
        dangerous_patterns = [
            (r"os\.", "禁止访问 os 模块"),
            (r"subprocess", "禁止访问 subprocess"),
            (r"open\s*\(", "禁止文件操作"),
            (r"__import__", "禁止动态导入"),
            (r"eval\s*\(", "禁止 eval"),
            (r"exec\s*\(", "禁止 exec"),
            (r"compile\s*\(", "禁止 compile"),
            (r"import\s+socket", "禁止网络操作"),
            (r"import\s+urllib", "禁止网络操作"),
            (r"import\s+requests", "禁止网络操作"),
        ]

        for pattern, message in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                errors.append(f"脚本安全检查: {message}")

        return errors

    def validate_asset_path(self, path: str) -> Tuple[bool, str]:
        """验证资源路径是否安全"""
        # 防止路径遍历
        normalized = path.replace("\\", "/")

        if ".." in normalized:
            return False, "路径包含目录遍历"

        if normalized.startswith("/"):
            return False, "绝对路径不允许"

        allowed_extensions = config.game_mod.supported_formats
        ext = "." + normalized.split(".")[-1].lower() if "." in normalized else ""
        if ext not in allowed_extensions:
            return False, f"不支持的文件格式: {ext}"

        return True, ""
