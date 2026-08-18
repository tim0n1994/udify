#!/usr/bin/env python3
"""入口点可达性门禁（FIT-01..04，iter7 M1）。

拦截「孤儿模块/孤儿符号」——有实现、有测试、ruff/mypy 全过，但**主路径从不调用**。
iter5→iter6 连续两轮出现「逻辑落地、接线展期」，测试数 +42 而产品行为零变化；
红线 #10「新增代码必须有测试」对这类代码完全失效，因为孤儿恰恰是有测试的。

为什么自建而不是用现成工具（见 docs/research-2026-08-iter7/DEEP-RESEARCH-REPORT-iter7.md §W1）：

- ``import-linter`` 的三类契约（layers/independence/forbidden）都是**禁止型**约束
  （"A 不许依赖 B"），而孤儿检测需要的是**要求型**约束（"必须被主路径调用"）。
  尤其 independence 契约恰好相反：孤儿簇内部**正是**互相依赖的。
- ``vulture`` 以**符号级被引用**为判据，孤儿簇内互引即算"已使用"，同样漏判。

两层判定（粒度经实测校准，缺一不可）：

1. **模块层**：``udify/`` 下的模块若无法从入口模块经 import 图到达 → 孤儿模块。
   实测可捕获 ``gate_orchestrator``(0 imports)、``target_resolver``(0 imports)。
2. **符号层**：可达模块内的公共顶层函数/类/方法，若其名字从未在**其它模块**中被
   引用 → 孤儿符号。实测必需——``runtime_probe``(4 imports)、``sandbox``(2 imports)
   模块本身可达，但 ``run_by_engine`` / ``execute_sandboxed`` 是其中的死方法，
   模块层完全漏判。

符号层是基于 AST 标识符引用的**保守近似**，不是真调用图：它统计 ``ast.Name.id`` 与
``ast.Attribute.attr``，因此会把"提到名字但没真调用"算作已使用（可能漏报），但极少
误报。这是刻意的取舍——门禁的价值在于零误报（否则会被加进 allowlist 忽略掉）。

用法::

    python3 scripts/check_reachability.py              # 检查，孤儿存在则退出码 1
    python3 scripts/check_reachability.py --write-baseline  # 冻结当前孤儿为已知债务
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "udify"
CONFIG_PATH = REPO_ROOT / ".udify-reachability.toml"

# 入口模块：pyproject 的 console_script (udify.cli:cli_entry) 与 serve 起的 API app。
# API 路由是 create_app 内的嵌套函数，经 cmd_serve → create_app 可达，无需单列。
ENTRY_MODULES = ("udify.cli", "udify.api.app")

# 符号层跳过：私有、dunder、以及由框架/协议约定调用而非显式调用的名字。
_SKIP_EXACT = frozenset({"main", "cli_entry", "create_app"})


@dataclass(frozen=True)
class Definition:
    """一个公共符号的定义位置。"""

    module: str
    name: str
    lineno: int
    kind: str  # "function" | "class" | "method"

    @property
    def qualname(self) -> str:
        return f"{self.module}:{self.name}"


@dataclass(frozen=True)
class AllowEntry:
    """allowlist 条目——三字段缺一不可，``expires`` 到期未清则 CI 红。"""

    symbol: str
    reason: str
    expires: dt.date


def module_name(path: Path) -> str:
    """文件路径 → 点分模块名（``udify/core/x.py`` → ``udify.core.x``）。"""
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def parse_all() -> dict[str, tuple[Path, ast.Module]]:
    """解析 ``udify/`` 下全部 .py，返回 {模块名: (路径, AST)}。"""
    out: dict[str, tuple[Path, ast.Module]] = {}
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # 语法错误让 ruff/mypy 报，这里不掩盖
            print(f"::warning:: 跳过无法解析的文件 {path}: {exc}")
            continue
        out[module_name(path)] = (path, tree)
    return out


def imports_of(tree: ast.Module, current: str, is_package: bool = False) -> set[str]:
    """抽取模块的 import 目标（含相对 import 解析、父包传递）。

    Python 导入 ``a.b.c`` 会执行 ``a`` 与 ``a.b`` 的 ``__init__``，因此父包也算可达。

    ``is_package`` 区分「模块」与「包 ``__init__``」——这决定相对 import 的锚点：
    模块 ``udify.core.mod`` 的 ``from .x`` 指向 ``udify.core.x``（同级），
    而包 ``udify.core`` 的 ``from .x`` 指向 ``udify.core.x``（其内部）。
    """
    found: set[str] = set()

    def add_with_parents(name: str) -> None:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            found.add(".".join(parts[:i]))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add_with_parents(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对 import
                base = current.split(".")
                # 包自身即 level=1 的锚点；普通模块要先退到其所在包
                depth = len(base) - node.level + (1 if is_package else 0)
                anchor = base[:depth] if depth > 0 else []
                target = ".".join(anchor + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if not target:
                continue
            add_with_parents(target)
            # ``from a.b import c`` 中 c 可能是子模块而非符号
            for alias in node.names:
                add_with_parents(f"{target}.{alias.name}")
    return {m for m in found if m.startswith("udify")}


def reachable_modules(parsed: dict[str, tuple[Path, ast.Module]]) -> set[str]:
    """从入口模块出发做 import 图 BFS，返回可达模块集合。"""
    seen: set[str] = set()
    queue = [m for m in ENTRY_MODULES if m in parsed]
    seen.update(queue)
    while queue:
        current = queue.pop()
        path, tree = parsed[current]
        for target in imports_of(tree, current, is_package=path.name == "__init__.py"):
            if target in parsed and target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _is_stub_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """函数体是否只是接口桩（``...`` / ``pass`` / 纯 docstring）。

    ``Protocol`` 与 ``ABC`` 的方法声明是**接口契约**而非调用点，不该按孤儿处理。
    用「体是不是桩」判定，比分析基类更简单也更通用（同时覆盖 Protocol/ABC/overload）。
    """
    for stmt in node.body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            if stmt.value.value is Ellipsis or isinstance(stmt.value.value, str):
                continue
        return False
    return True


def definitions_of(module: str, tree: ast.Module) -> list[Definition]:
    """抽取公共顶层函数/类，以及类内公共方法。

    跳过私有（``_`` 前缀）、dunder 与接口桩方法；FastAPI 路由是 ``create_app`` 内的
    嵌套函数，不在顶层，天然被跳过（这正是所需的框架感知）。
    """
    defs: list[Definition] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if not node.name.startswith("_") and not _is_stub_body(node):
                defs.append(Definition(module, node.name, node.lineno, "function"))
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            defs.append(Definition(module, node.name, node.lineno, "class"))
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                    if not sub.name.startswith("_") and not _is_stub_body(sub):
                        defs.append(Definition(module, sub.name, sub.lineno, "method"))
    return defs


def referenced_names(tree: ast.Module) -> set[str]:
    """模块内引用到的全部标识符（``Name.id`` + ``Attribute.attr`` + import 的别名）。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def load_allowlist(path: Path | None = None) -> tuple[list[AllowEntry], list[str]]:
    """读取 allowlist；返回 (条目, 格式错误列表)。三字段缺一即错。"""
    config = path or CONFIG_PATH
    if not config.exists():
        return [], []
    data = tomllib.loads(config.read_text(encoding="utf-8"))
    entries: list[AllowEntry] = []
    errors: list[str] = []
    for raw in data.get("allow", []):
        symbol = raw.get("symbol")
        reason = raw.get("reason")
        expires = raw.get("expires")
        if not symbol:
            errors.append(f"allowlist 条目缺 symbol: {raw!r}")
            continue
        if not reason:
            errors.append(f"{symbol}: 缺 reason（禁止空串——豁免必须写明理由）")
            continue
        if not isinstance(expires, dt.date):
            errors.append(f"{symbol}: expires 必须是 TOML 日期（如 2026-09-30），当前 {expires!r}")
            continue
        entries.append(AllowEntry(symbol, reason, expires))
    return entries, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="入口点可达性门禁（FIT-01..04）")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="把当前孤儿冻结进 allowlist（渐进启用：只阻塞新增孤儿）",
    )
    parser.add_argument(
        "--expires",
        default="",
        help="配合 --write-baseline 使用的过期日期（ISO，默认 90 天后）",
    )
    args = parser.parse_args()

    parsed = parse_all()
    if not parsed:
        print("❌ 未找到任何 udify/ 模块")
        return 1

    reachable = reachable_modules(parsed)

    # 第 1 层：孤儿模块
    orphan_modules = sorted(set(parsed) - reachable)

    # 第 2 层：可达模块内的孤儿符号
    refs_by_module = {m: referenced_names(tree) for m, (_, tree) in parsed.items()}
    orphan_symbols: list[Definition] = []
    for module in sorted(reachable):
        _, tree = parsed[module]
        for defn in definitions_of(module, tree):
            if defn.name in _SKIP_EXACT:
                continue
            # 同模块引用也算「已使用」：``cmd_mod`` 只在 cli.py 的 commands 字典里被
            # 引用，但 cli.py 是入口模块，那条路径是真的。``def foo`` 本身不产生
            # Name/Attribute 节点，因此定义自身不会被误计为引用。
            used = any(defn.name in refs for refs in refs_by_module.values())
            if not used:
                orphan_symbols.append(defn)

    found = [f"module:{m}" for m in orphan_modules] + [d.qualname for d in orphan_symbols]

    if args.write_baseline:
        expires = args.expires or (dt.date.today() + dt.timedelta(days=90)).isoformat()
        lines = [
            "# 可达性门禁 allowlist（FIT-03）。",
            "# 每条必须有 symbol / reason / expires 三字段；expires 到期未清 = CI 红。",
            "# 过期日期把「展期」从静默动作变成必须显式续签的动作。",
            "",
        ]
        for item in found:
            lines += [
                "[[allow]]",
                f'symbol = "{item}"',
                'reason = "iter7 基线：接线前的已知债务，由 iter7 M2/M3 清零"',
                f"expires = {expires}",
                "",
            ]
        CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")
        print(f"✅ 已写入基线 {CONFIG_PATH.name}：{len(found)} 条，过期日 {expires}")
        return 0

    allow_entries, allow_errors = load_allowlist()
    today = dt.date.today()
    allowed = {e.symbol for e in allow_entries}
    expired = [e for e in allow_entries if e.expires < today]

    new_orphans = [f for f in found if f not in allowed]

    ok = True
    if allow_errors:
        ok = False
        print("❌ allowlist 格式错误：")
        for err in allow_errors:
            print(f"   - {err}")

    if expired:
        ok = False
        print(f"❌ allowlist 有 {len(expired)} 条已过期（到期未清 = 红线 #16）：")
        for e in expired:
            print(f"   - {e.symbol}（{e.expires} 过期）：{e.reason}")

    if new_orphans:
        ok = False
        print(f"❌ 发现 {len(new_orphans)} 个无主路径调用者的模块/符号（红线 #16）：")
        for item in new_orphans:
            print(f"   - {item}")
        print()
        print("   修法（按优先级）：1) 接进主路径  2) 删除  3) 加 allowlist 并写明理由与过期日")

    if ok:
        total = len(parsed)
        print(
            f"✅ 可达性检查通过：{total} 模块，{len(reachable)} 可达，"
            f"{len(found)} 已知孤儿全部在 allowlist 内"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
