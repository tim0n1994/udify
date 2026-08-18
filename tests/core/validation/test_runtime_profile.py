"""RuntimeProfile + 目录发现测试（iter3 N5）。

discover_web_root 测试不依赖 Playwright，始终跑。
probe_runtime_profile 测试在无 Playwright 时 skip（不伪造通过）。
"""

from pathlib import Path

import pytest

from udify.core.validation.playwright_probe import discover_web_root


def _web_root(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    root.mkdir()
    (root / "index.html").write_text("<script>window.$dataEnemies=[{hp:9999}]</script>")
    return root


def test_discover_web_root_finds_index(tmp_path):
    found = discover_web_root(_web_root(tmp_path))
    assert found is not None
    assert (found / "index.html").is_file()


def test_discover_web_root_www_subdir(tmp_path):
    root = tmp_path / "proj"
    (root / "www").mkdir(parents=True)
    (root / "www" / "index.html").write_text("<html></html>")
    found = discover_web_root(root)
    assert found is not None
    assert found.name == "www"


def test_discover_web_root_none_when_absent(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    assert discover_web_root(root) is None


def _need_playwright():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            b.close()
    except Exception:
        pytest.skip("chromium not installed")


def test_probe_and_assertions(tmp_path):
    _need_playwright()
    from udify.core.validation.playwright_probe import (
        PlaywrightProbeSpec,
        assertions_from_profile,
        probe_runtime_profile,
    )

    root = _web_root(tmp_path)
    spec = PlaywrightProbeSpec(
        web_root=root,
        entry="index.html",
        ready_expr="window.$dataEnemies !== undefined",
    )
    profile = probe_runtime_profile(spec)
    assert profile.ready is True
    assert "$dataEnemies" in profile.globals_found
    asserts = assertions_from_profile(profile, "$dataEnemies", "[0].hp", 9999)
    assert len(asserts) == 1
    assert assertions_from_profile(profile, "$nonexistent", ".x", 1) == []
