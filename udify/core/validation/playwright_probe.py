"""
真 Playwright 运行时探针（VAL-RUNTIME-06，欠条 B 清偿）。

与 HeadlessRuntimeProbe（模拟）不同，本探针真正启动 patched miu2d web build、
读取运行时对象、断言修改生效（Level 2：启动游戏读运行时状态）。

诚实设计：playwright 未安装时抛明确错误，绝不伪造通过；测试层用
pytest.importorskip 跳过。无 Playwright 环境下不应声称做了运行时验证。
"""

from __future__ import annotations

import http.server
import socketserver
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from udify.core.validation.runtime_probe import ProbeReport, ProbeResult, ProbeSpec


class PlaywrightUnavailableError(RuntimeError):
    """playwright 未安装或浏览器未就绪。调用方应降级或 skip，不可伪造通过。"""


@dataclass
class RuntimeAssertion:
    """一条运行时断言：读哪个表达式、期望什么值。"""

    expr: str  # 在页面里 evaluate 的 JS 表达式（如 "window.$dataEnemies[1].hp"）
    expected: Any
    label: str = ""


@dataclass
class PlaywrightProbeSpec:
    """Playwright 探针规格（Level 2）。"""

    web_root: Path  # patched web tree 的本地根目录
    entry: str = "index.html"  # 相对 web_root 的入口
    ready_expr: str = "document.readyState === 'complete'"  # 加载完成判定
    assertions: list[RuntimeAssertion] = field(default_factory=list)
    timeout_ms: int = 15000


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # 静默
        pass


class PlaywrightRuntimeProbe:
    """真 Playwright 运行时探针。

    流程：起 stdlib 静态服务 web_root -> Playwright 打开入口 -> 等待 ready ->
    逐条 evaluate 断言表达式 -> 捕获 console error -> 返回 ProbeReport。
    """

    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:  # pragma: no cover - 环境相关
            raise PlaywrightUnavailableError(
                "playwright is not installed; install with: pip install playwright && playwright install chromium"
            ) from exc
        self._sync_playwright_mod = "playwright.sync_api"

    def run(self, spec: PlaywrightProbeSpec, probes: list[ProbeSpec] | None = None) -> ProbeReport:
        from playwright.sync_api import sync_playwright

        report = ProbeReport()
        port = self._free_port()
        cwd = str(spec.web_root)
        httpd = socketserver.TCPServer(("127.0.0.1", port), _Handler)
        httpd.directory = cwd  # type: ignore[attr-defined]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        url = f"http://127.0.0.1:{port}/{spec.entry.lstrip('/')}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                console_errors: list[str] = []
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
                )
                page.on("pageerror", lambda err: console_errors.append(str(err)))
                page.goto(url, wait_until="domcontentloaded", timeout=spec.timeout_ms)
                page.wait_for_function(spec.ready_expr, timeout=spec.timeout_ms)
                report.game_started = True
                report.state_readable = True

                for i, assertion in enumerate(spec.assertions):
                    try:
                        observed = page.evaluate(assertion.expr)
                    except Exception as exc:  # 表达式读不到
                        from udify.core.validation.runtime_probe import ProbeKind

                        report.results.append(
                            ProbeResult(
                                probe_id=f"assert_{i}",
                                passed=False,
                                kind=ProbeKind.READ_STATE,
                                observed={},
                                evidence=f"evaluate failed: {exc}",
                            )
                        )
                        continue
                    passed = observed == assertion.expected
                    report.results.append(
                        ProbeResult(
                            probe_id=f"assert_{i}",
                            passed=passed,
                            observed={"expr": assertion.expr, "value": observed},
                            evidence=assertion.label or assertion.expr,
                        )
                    )
                report.console_error_count = len(console_errors)
                # 把 console error 附到最后一条结果
                if console_errors and report.results:
                    report.results[-1].console_errors = console_errors
                browser.close()
        finally:
            httpd.shutdown()
            server_thread.join(timeout=5)

        report.passed = (
            report.game_started
            and report.state_readable
            and report.console_error_count == 0
            and all(r.passed for r in report.results)
        )
        return report

    @staticmethod
    def _free_port() -> int:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port


__all__ = [
    "PlaywrightProbeSpec",
    "PlaywrightRuntimeProbe",
    "PlaywrightUnavailableError",
    "RuntimeAssertion",
]


def discover_web_root(game_root: Path) -> Path | None:
    """目录发现器（iter3 N5 / S2-MIU2D）。

    确定 miu2d 的真实 web 服务根目录。不假设 game_root=web_root：
    检查根 index.html，再检查 www/。拒绝符号链接（防逃逸）。
    """
    root = Path(game_root)
    candidates = [root, root / "www"]
    for c in candidates:
        entry = c / "index.html"
        try:
            if entry.is_file() and not entry.is_symlink() and not c.is_symlink():
                resolved = entry.resolve(strict=False)
                # 确保解析后仍在 game_root 内（防 symlink 逃逸）
                try:
                    resolved.relative_to(root.resolve(strict=False))
                except ValueError:
                    continue
                return c
        except (OSError, RuntimeError):
            continue
    return None


@dataclass
class RuntimeProfile:
    """运行时对象探测结果（iter3 N5）。

    因 miu2d 运行时全局对象未经真实确认，不写死 $dataEnemies 等契约；
    加载后扫描 window 上存在的游戏相关全局对象，物化为 profile，
    断言表达式从 profile 动态生成（诚实、不臆造）。
    """

    globals_found: dict[str, Any] = field(default_factory=dict)
    web_root: Path | None = None
    ready: bool = False


def probe_runtime_profile(spec: PlaywrightProbeSpec) -> RuntimeProfile:
    """扫描 miu2d web build 的 window 全局对象，物化 RuntimeProfile。

    扫描 window 上以 $ 或 game/data/enemy/actor 开头的键（RPG Maker 风格候选），
    记录其存在与浅形状（类型/长度）。无 Playwright 时抛 PlaywrightUnavailableError。
    """
    profile = RuntimeProfile(web_root=spec.web_root, ready=False)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlaywrightUnavailableError("playwright not installed") from exc

    port = PlaywrightRuntimeProbe._free_port()
    httpd = socketserver.TCPServer(("127.0.0.1", port), _Handler)
    httpd.directory = str(spec.web_root)  # type: ignore[attr-defined]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}/{spec.entry.lstrip('/')}"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=spec.timeout_ms)
            page.wait_for_function(spec.ready_expr, timeout=spec.timeout_ms)
            profile.ready = True
            # 扫描 window 全局对象（候选：$ 开头 或 game/data/enemy/actor 命名）
            found = page.evaluate(
                """() => {
                    const out = {};
                    for (const k of Object.keys(window)) {
                        if (/^[$]/.test(k) || /^(game|data|enemy|actor|troop)/i.test(k)) {
                            try {
                                const v = window[k];
                                out[k] = { type: typeof v,
                                           isArray: Array.isArray(v),
                                           len: Array.isArray(v) ? v.length : null };
                            } catch (e) { out[k] = { type: 'inaccessible' }; }
                        }
                    }
                    return out;
                }"""
            )
            profile.globals_found = dict(found) if isinstance(found, dict) else {}
            browser.close()
    finally:
        httpd.shutdown()
        t.join(timeout=5)
    return profile


def assertions_from_profile(
    profile: RuntimeProfile, target_global: str, field: str, expected: Any
) -> list[RuntimeAssertion]:
    """从 RuntimeProfile 动态生成断言（不臆造固定契约）。

    若 target_global 在 profile.globals_found 中，生成一个断言表达式
    ``window.<global>[<field>]``；否则返回空（调用方降级）。
    """
    if target_global not in profile.globals_found:
        return []
    expr = f"window['{target_global}']{field}"
    return [RuntimeAssertion(expr=expr, expected=expected, label=f"{target_global}{field}")]
