"""seatbelt 沙箱 + fail-closed 测试（iter3 N3 / S4-SANDBOX）。"""

from pathlib import Path

from udify.core.tool_gateway.audit import ToolAuditChain
from udify.core.tool_gateway.gateway import ToolCallRequest, ToolGateway
from udify.core.tool_gateway.policy import ToolPolicy
from udify.core.tool_gateway.sandbox import SandboxExecutor, SandboxProfile


class FakeSandbox:
    """假沙箱：可控返回，模拟 seatbelt 可用/不可用。"""

    def __init__(self, blocked_reason=None, success=True, stdout=""):
        self.blocked_reason = blocked_reason
        self.success = success
        self.stdout = stdout
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        from udify.core.tool_gateway.gateway import ToolCallResult

        return ToolCallResult(
            success=self.success,
            return_code=0 if self.success else None,
            stdout=self.stdout,
            blocked_reason=self.blocked_reason or "",
        )


def _gw(tmp_path):
    policy = ToolPolicy(allowed_roots=[Path(str(tmp_path))])
    audit = ToolAuditChain()
    return ToolGateway(policy=policy, audit=audit), audit


def test_r3_sandboxed_executes_via_sandbox(tmp_path):
    gw, audit = _gw(tmp_path)
    sb = FakeSandbox(success=True, stdout="sandboxed-out")
    req = ToolCallRequest(tool_id="runner", capability="run_external_tool", args=["echo", "hi"])
    res = gw.call_sandboxed(req, sb, human_approved=True)
    assert res.success
    assert "sandboxed-out" in res.stdout
    assert len(sb.calls) == 1


def test_r3_without_approval_blocked(tmp_path):
    gw, audit = _gw(tmp_path)
    sb = FakeSandbox()
    req = ToolCallRequest(tool_id="runner", capability="run_external_tool", args=["x"])
    res = gw.call_sandboxed(req, sb, human_approved=False)
    assert not res.success
    assert "human" in res.blocked_reason
    assert len(sb.calls) == 0


def test_fail_closed_when_sandbox_unavailable(tmp_path):
    """S4 红线：沙箱不可用不降级为普通 subprocess。"""
    gw, audit = _gw(tmp_path)
    sb = FakeSandbox(blocked_reason="seatbelt_unavailable", success=False)
    req = ToolCallRequest(tool_id="runner", capability="run_external_tool", args=["x"])
    res = gw.call_sandboxed(req, sb, human_approved=True)
    assert not res.success
    assert "fail-closed" in res.blocked_reason or "no degrade" in res.blocked_reason


def test_r4_not_approvable_in_sandbox_path(tmp_path):
    gw, audit = _gw(tmp_path)
    sb = FakeSandbox()
    req = ToolCallRequest(tool_id="net", capability="network", args=["curl"])
    res = gw.call_sandboxed(req, sb, human_approved=True)
    assert not res.success
    assert "R4" in res.blocked_reason
    assert len(sb.calls) == 0


def test_audit_covers_sandboxed_call(tmp_path):
    gw, audit = _gw(tmp_path)
    sb = FakeSandbox(success=True)
    req = ToolCallRequest(tool_id="runner", capability="run_external_tool", args=["x"])
    gw.call_sandboxed(req, sb, human_approved=True)
    assert len(audit.records()) == 1


def test_real_sandbox_executor_runs_readonly(tmp_path):
    """真 SandboxExecutor：用 /bin/echo 这类只读命令验证 seatbelt/restricted 后端可跑。"""
    gw, audit = _gw(tmp_path)
    profile = SandboxProfile(
        allowed_read_roots=[Path(str(tmp_path))],
        allowed_write_roots=[Path(str(tmp_path))],
    )
    executor = SandboxExecutor(profile=profile)
    req = ToolCallRequest(
        tool_id="runner", capability="run_external_tool", args=["/bin/echo", "ok"]
    )
    res = gw.call_sandboxed(req, executor, human_approved=True)
    # echo 在受限/seatbelt 后端都应成功
    assert res.success
    assert "ok" in res.stdout
