"""
Secure Tool Gateway 测试（TOOL-GW-01..06）。

覆盖批次 1 验收标准：
- 越权路径被拒（path allowlist）
- 一个真实工具调用走 gateway
- 审计链完整可校验
- 风险分级驱动决策
- 锁文件 pin 校验

对应 ITERATION-PLAN-2026-07.md §4.3。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from udify.core.tool_gateway import (
    RiskLevel,
    ToolAuditChain,
    ToolCallRequest,
    ToolGateway,
    ToolLockfile,
    ToolPin,
    ToolPolicy,
)
from udify.core.tool_gateway.audit import ToolCallRecord, now_iso


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    game_root = tmp_path / "game"
    game_root.mkdir()
    (game_root / "data.ini").write_text("[Boss]\nhp=500\n")
    return tmp_path


class TestPolicyPathAllowlist:
    """路径 allowlist：越权路径被拒（成功判据 #4 的安全基础）"""

    def test_allows_path_in_game_root(self, workspace: Path) -> None:
        game_root = workspace / "game"
        policy = ToolPolicy(allowed_roots=[game_root])
        decision = policy.evaluate(
            tool_id="converter",
            capability="read_file",
            requested_paths=[game_root / "data.ini"],
        )
        assert decision.allowed

    def test_blocks_path_outside_roots(self, workspace: Path) -> None:
        game_root = workspace / "game"
        policy = ToolPolicy(allowed_roots=[game_root])
        # 试图读取 /etc/passwd（越权）
        decision = policy.evaluate(
            tool_id="converter",
            capability="read_file",
            requested_paths=[Path("/etc/passwd")],
        )
        assert not decision.allowed
        assert "outside allowed roots" in decision.reason

    def test_blocks_parent_traversal(self, workspace: Path) -> None:
        game_root = workspace / "game"
        policy = ToolPolicy(allowed_roots=[game_root])
        decision = policy.evaluate(
            tool_id="converter",
            capability="read_file",
            requested_paths=[game_root / ".." / "secret.txt"],
        )
        assert not decision.allowed


class TestPolicyRiskLevels:
    """风险分级驱动决策（R0-R4）"""

    def test_r0_read_auto_allowed(self, workspace: Path) -> None:
        policy = ToolPolicy(allowed_roots=[workspace])
        decision = policy.evaluate(tool_id="x", capability="read_file")
        assert decision.allowed
        assert decision.risk == RiskLevel.R0

    def test_r4_runtime_hook_requires_human(self, workspace: Path) -> None:
        policy = ToolPolicy(allowed_roots=[workspace])
        decision = policy.evaluate(tool_id="x", capability="runtime_hook")
        assert not decision.allowed
        assert decision.requires_human_confirmation
        assert decision.risk == RiskLevel.R4

    def test_r3_run_external_requires_sandbox(self, workspace: Path) -> None:
        policy = ToolPolicy(allowed_roots=[workspace])
        decision = policy.evaluate(tool_id="x", capability="run_external_tool")
        # R3 >= require_confirmation_above(R3) → 需人工
        assert decision.requires_human_confirmation
        assert decision.sandbox_required

    def test_network_default_blocked(self, workspace: Path) -> None:
        policy = ToolPolicy(allowed_roots=[workspace])
        decision = policy.evaluate(tool_id="x", capability="network")
        assert decision.risk == RiskLevel.R4
        assert not decision.network_allowed


class TestGatewayExecution:
    """一个真实工具调用走 gateway"""

    def test_real_call_through_gateway(self, workspace: Path) -> None:
        """调用 `python --version` 走 gateway（read 类，R0）"""
        policy = ToolPolicy(allowed_roots=[workspace])
        gw = ToolGateway(policy=policy, audit=ToolAuditChain())
        req = ToolCallRequest(
            tool_id="python",
            capability="read_file",
            args=[sys.executable, "--version"],
        )
        result = gw.call(req)
        assert result.success
        assert result.return_code == 0
        assert "Python" in result.stdout

    def test_blocked_call_recorded_as_blocked(self, workspace: Path) -> None:
        game_root = workspace / "game"
        policy = ToolPolicy(allowed_roots=[game_root])
        gw = ToolGateway(policy=policy, audit=ToolAuditChain())
        req = ToolCallRequest(
            tool_id="cat",
            capability="read_file",
            args=["cat", "/etc/passwd"],
            requested_paths=[Path("/etc/passwd")],
        )
        result = gw.call(req)
        assert not result.success
        assert "outside allowed roots" in result.blocked_reason
        # 审计记录了这次拦截
        records = gw.audit.records()
        assert len(records) == 1
        assert records[0].decision == "blocked"

    def test_call_with_runner_injection(self, workspace: Path) -> None:
        """上层可注入沙箱 runner，网关仍负责策略+审计"""
        policy = ToolPolicy(allowed_roots=[workspace])
        gw = ToolGateway(policy=policy, audit=ToolAuditChain())

        def fake_sandbox_runner(req: ToolCallRequest) -> ToolCallResult:  # noqa: F821
            from udify.core.tool_gateway import ToolCallResult as R

            return R(success=True, return_code=0, stdout="sandboxed output")

        req = ToolCallRequest(tool_id="x", capability="read_file", args=["x"])
        result = gw.call_with_runner(req, fake_sandbox_runner)
        assert result.success
        assert "sandboxed" in result.stdout


class TestAuditChain:
    """审计链完整可校验"""

    def test_chain_verifies_after_appends(self) -> None:
        chain = ToolAuditChain()
        for _ in range(3):
            chain.append(
                ToolCallRecord(
                    timestamp=now_iso(),
                    tool_id="t",
                    capability="read_file",
                    args={},
                    requested_paths=[],
                    risk="R0",
                    decision="allowed",
                    success=True,
                    return_code=0,
                )
            )
        assert len(chain.records()) == 3
        assert chain.verify()

    def test_tamper_breaks_chain(self) -> None:
        chain = ToolAuditChain()
        chain.append(
            ToolCallRecord(
                timestamp=now_iso(),
                tool_id="t",
                capability="read_file",
                args={},
                requested_paths=[],
                risk="R0",
                decision="allowed",
                success=True,
            )
        )
        chain._records[0].success = False  # 篡改
        assert not chain.verify()

    def test_chain_persists_to_disk(self, tmp_path: Path) -> None:
        store = tmp_path / "audit.json"
        chain = ToolAuditChain(store_path=store)
        chain.append(
            ToolCallRecord(
                timestamp=now_iso(),
                tool_id="t",
                capability="read_file",
                args={},
                requested_paths=[],
                risk="R0",
                decision="allowed",
                success=True,
            )
        )
        # 重新加载
        chain2 = ToolAuditChain(store_path=store)
        assert len(chain2.records()) == 1
        assert chain2.verify()


class TestLockfile:
    """工具锁文件 pin（TOOL-GW-07）"""

    def test_pin_and_verify_match(self) -> None:
        lf = ToolLockfile()
        lf.add(ToolPin(tool_id="converter", version="1.0", sha256="abc123"))
        assert lf.verify("converter", "abc123")

    def test_verify_mismatch(self) -> None:
        lf = ToolLockfile()
        lf.add(ToolPin(tool_id="converter", version="1.0", sha256="abc123"))
        assert not lf.verify("converter", "tampered")

    def test_verify_unknown_tool_fails(self) -> None:
        lf = ToolLockfile()
        assert not lf.verify("unlocked_tool", "anything")

    def test_lockfile_save_load_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "lock.json"
        lf = ToolLockfile()
        lf.add(ToolPin(tool_id="converter", version="1.0", sha256="abc"))
        lf.save(path)
        lf2 = ToolLockfile.load(path)
        assert lf2.get("converter") is not None
        assert lf2.get("converter").sha256 == "abc"  # type: ignore[union-attr]
