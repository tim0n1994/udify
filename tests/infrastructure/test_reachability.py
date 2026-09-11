"""可达性门禁的行为锁（FIT-01..04，iter7 M1）。

这些测试锁住的是**校准结论**：门禁的价值在于零误报（有误报就会被塞进 allowlist
忽略掉），因此正/负对照是核心断言，不是锦上添花。
"""

from __future__ import annotations

import ast
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_reachability", REPO_ROOT / "scripts" / "check_reachability.py"
)
assert _SPEC and _SPEC.loader
reach = importlib.util.module_from_spec(_SPEC)
sys.modules["check_reachability"] = reach
_SPEC.loader.exec_module(reach)


def _defs(source: str) -> list[str]:
    return [d.name for d in reach.definitions_of("m", ast.parse(source))]


class TestStubSkipping:
    """Protocol/ABC 的方法声明是接口契约，不是调用点——不得按孤儿处理。"""

    def test_protocol_ellipsis_stub_skipped(self) -> None:
        src = "from typing import Protocol\nclass A(Protocol):\n    def emit(self) -> None: ...\n"
        assert "emit" not in _defs(src)

    def test_docstring_only_stub_skipped(self) -> None:
        src = 'class A:\n    def emit(self) -> None:\n        """契约声明。"""\n'
        assert "emit" not in _defs(src)

    def test_pass_stub_skipped(self) -> None:
        src = "class A:\n    def emit(self) -> None:\n        pass\n"
        assert "emit" not in _defs(src)

    def test_real_body_not_skipped(self) -> None:
        src = "class A:\n    def emit(self) -> int:\n        return 1\n"
        assert "emit" in _defs(src)

    def test_private_and_dunder_skipped(self) -> None:
        src = "class A:\n    def _h(self) -> int:\n        return 1\n"
        assert _defs(src) == ["A"]


class TestDefinitionScope:
    """FastAPI 路由是 create_app 内的嵌套函数——天然不在顶层，这正是所需的框架感知。"""

    def test_nested_function_not_collected(self) -> None:
        src = "def create_app():\n    def route():\n        return 1\n    return route\n"
        assert _defs(src) == ["create_app"]


class TestImports:
    def test_import_marks_parent_packages(self) -> None:
        found = reach.imports_of(ast.parse("from udify.core.a.b import C"), "udify.x")
        assert {"udify", "udify.core", "udify.core.a", "udify.core.a.b"} <= found

    def test_relative_import_from_module_anchors_at_its_package(self) -> None:
        found = reach.imports_of(ast.parse("from .sibling import X"), "udify.core.mod")
        assert "udify.core.sibling" in found

    def test_relative_import_from_package_anchors_at_itself(self) -> None:
        found = reach.imports_of(ast.parse("from .sub import X"), "udify.core", is_package=True)
        assert "udify.core.sub" in found

    def test_non_udify_imports_ignored(self) -> None:
        assert reach.imports_of(ast.parse("import os, json"), "udify.x") == set()


class TestReferences:
    def test_name_and_attribute_collected(self) -> None:
        refs = reach.referenced_names(ast.parse("foo()\nbar.baz()\n"))
        assert {"foo", "bar", "baz"} <= refs

    def test_definition_itself_is_not_a_reference(self) -> None:
        """``def foo`` 不产生 Name 节点——否则每个符号都会自证"已使用"。"""
        assert "foo" not in reach.referenced_names(ast.parse("def foo():\n    return 1\n"))


class TestAllowlist:
    """三字段缺一即错；过期未清 = CI 红（红线 #16 的执行机制）。"""

    def _write(self, tmp_path: Path, body: str) -> Path:
        p = tmp_path / "allow.toml"
        p.write_text(body, encoding="utf-8")
        return p

    def test_missing_reason_is_error(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, '[[allow]]\nsymbol = "m:s"\nexpires = 2099-01-01\n')
        entries, errors = reach.load_allowlist(p)
        assert not entries and any("reason" in e for e in errors)

    def test_missing_expires_is_error(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, '[[allow]]\nsymbol = "m:s"\nreason = "r"\n')
        entries, errors = reach.load_allowlist(p)
        assert not entries and any("expires" in e for e in errors)

    def test_string_expires_rejected(self, tmp_path: Path) -> None:
        """必须是 TOML 日期而非字符串，否则无法做过期比较。"""
        p = self._write(
            tmp_path, '[[allow]]\nsymbol = "m:s"\nreason = "r"\nexpires = "2099-01-01"\n'
        )
        entries, errors = reach.load_allowlist(p)
        assert not entries and errors

    def test_valid_entry_parsed(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, '[[allow]]\nsymbol = "m:s"\nreason = "r"\nexpires = 2099-01-01\n')
        entries, errors = reach.load_allowlist(p)
        assert not errors
        assert entries[0].symbol == "m:s"
        assert entries[0].expires == dt.date(2099, 1, 1)

    def test_missing_file_is_empty_not_error(self, tmp_path: Path) -> None:
        assert reach.load_allowlist(tmp_path / "nope.toml") == ([], [])


class TestRealRepoCalibration:
    """对真实仓库的正/负对照——这是门禁可信度的证据，退化即失效。"""

    @staticmethod
    @pytest.fixture(scope="module")
    def scan() -> tuple[set[str], set[str]]:
        parsed = reach.parse_all()
        reachable = reach.reachable_modules(parsed)
        orphan_modules = set(parsed) - reachable
        refs = {m: reach.referenced_names(t) for m, (_, t) in parsed.items()}
        orphan_symbols = {
            d.qualname
            for m in reachable
            for d in reach.definitions_of(m, parsed[m][1])
            if d.name not in reach._SKIP_EXACT and not any(d.name in r for r in refs.values())
        }
        return orphan_modules, orphan_symbols

    def test_entry_modules_are_reachable(self, scan: tuple[set[str], set[str]]) -> None:
        orphan_modules, _ = scan
        assert "udify.cli" not in orphan_modules
        assert "udify.api.app" not in orphan_modules

    @pytest.mark.parametrize(
        "module",
        [
            "udify.core.cognition.target_resolver",
            "udify.core.orchestration.gate_orchestrator",
        ],
    )
    def test_iter7_wired_modules_are_no_longer_orphans(
        self, scan: tuple[set[str], set[str]], module: str
    ) -> None:
        """iter7 已接线模块的回归锁——退回孤儿即代表接线被撤掉了。

        ``target_resolver`` 由 M2-PR1 接入 ``pipeline.py`` 第 4b 步；
        ``gate_orchestrator`` 由 M3-PR1 接入 ``job_runner.approve`` 的 validating 阶段。
        两者都曾在 iter5/iter6 连续两轮 PRD 中被宣布接线而实际零调用者，
        因此这两条断言的价值是防止第三次复发。
        """
        orphan_modules, _ = scan
        assert module not in orphan_modules

    def test_static_package_path_does_not_execute_original_game(
        self, scan: tuple[set[str], set[str]]
    ) -> None:
        _, orphan_symbols = scan
        assert "udify.core.validation.runtime_probe:run_by_engine" in orphan_symbols

    def test_known_orphan_symbol_still_detected(self, scan: tuple[set[str], set[str]]) -> None:
        """正对照：模块可达但方法是死的——符号层的存在理由。

        ``execute_sandboxed`` 仍未接线（不在 iter7 范围），保留作为门禁灵敏度的活证据。
        """
        _, orphan_symbols = scan
        assert "udify.core.execution.sandbox:execute_sandboxed" in orphan_symbols

    def test_main_path_symbols_not_flagged(self, scan: tuple[set[str], set[str]]) -> None:
        """负对照：主路径活跃符号零误报，否则门禁会被 allowlist 淹没。"""
        orphan_modules, orphan_symbols = scan
        flagged = orphan_modules | {s.split(":")[-1] for s in orphan_symbols}
        for name in ("Miu2dClosedLoop", "JobStore", "JobRunner", "create_app"):
            assert name not in flagged
