"""真 Playwright 探针测试（VAL-RUNTIME-06 / 欠条 B）。

无 Playwright 环境下用 pytest.importorskip 跳过，绝不伪造通过。
"""

from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright")

from udify.core.validation.playwright_probe import (  # noqa: E402
    PlaywrightProbeSpec,
    PlaywrightRuntimeProbe,
    RuntimeAssertion,
)


def _fake_web_root(tmp_path: Path) -> Path:
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text(
        "<!doctype html><html><head><script>"
        "window.__UDIFY_TEST__ = { bossHp: 9999, heroHp: 800 };"
        "</script></head><body>ok</body></html>"
    )
    return root


@pytest.fixture(scope="module")
def browser_ready():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            b = pw.chromium.launch()
            b.close()
        return True
    except Exception:
        pytest.skip("chromium not installed")


def test_probe_reads_runtime_and_passes(tmp_path, browser_ready):
    root = _fake_web_root(tmp_path)
    probe = PlaywrightRuntimeProbe()
    spec = PlaywrightProbeSpec(
        web_root=root,
        entry="index.html",
        ready_expr="window.__UDIFY_TEST__ !== undefined",
        assertions=[
            RuntimeAssertion(expr="window.__UDIFY_TEST__.bossHp", expected=9999, label="boss hp"),
            RuntimeAssertion(expr="window.__UDIFY_TEST__.heroHp", expected=800, label="hero hp"),
        ],
    )
    report = probe.run(spec)
    assert report.game_started is True
    assert report.state_readable is True
    assert all(r.passed for r in report.results)
    assert report.passed is True


def test_probe_reports_failure_on_wrong_value(tmp_path, browser_ready):
    root = _fake_web_root(tmp_path)
    probe = PlaywrightRuntimeProbe()
    spec = PlaywrightProbeSpec(
        web_root=root,
        entry="index.html",
        ready_expr="window.__UDIFY_TEST__ !== undefined",
        assertions=[
            RuntimeAssertion(expr="window.__UDIFY_TEST__.bossHp", expected=1, label="should fail"),
        ],
    )
    report = probe.run(spec)
    assert report.game_started is True
    assert report.passed is False
    assert any(not r.passed for r in report.results)


def test_probe_does_not_fake_pass_on_missing_object(tmp_path, browser_ready):
    root = _fake_web_root(tmp_path)
    probe = PlaywrightRuntimeProbe()
    spec = PlaywrightProbeSpec(
        web_root=root,
        entry="index.html",
        ready_expr="window.__UDIFY_TEST__ !== undefined",
        assertions=[
            RuntimeAssertion(expr="window.__NONEXISTENT__.x", expected=5),
        ],
    )
    report = probe.run(spec)
    assert report.passed is False
