"""安全 Agent 循环测试（AGENT-LOOP-01..04）。"""

from pathlib import Path

from udify.core.execution.agent_loop import AgentAction, AgentLoop, AgentState
from udify.core.tool_gateway.audit import ToolAuditChain
from udify.core.tool_gateway.gateway import ToolGateway
from udify.core.tool_gateway.policy import ToolPolicy


def _make_gateway(tmp_path, allowed_root):
    policy = ToolPolicy(allowed_roots=[Path(str(allowed_root))])
    audit = ToolAuditChain(store_path=Path(str(tmp_path / "audit.json")))
    return ToolGateway(policy=policy, audit=audit), audit


def _write_tool(tmp_path):
    tool = tmp_path / "echo_ok.sh"
    tool.write_text("#!/bin/sh\necho ok\n")
    tool.chmod(0o755)
    return tool


def _plan_reader(target):
    def plan(_ctx):
        return [
            AgentAction(
                tool_id="reader",
                capability="read_file",
                args=["cat", str(target)],
                requested_paths=[str(target)],
            )
        ]

    return plan


def _plan_runner(tool):
    def plan(_ctx):
        return [AgentAction(tool_id="runner", capability="run_external_tool", args=[str(tool)])]

    return plan


def _plan_true():
    def plan(_ctx):
        return [AgentAction(tool_id="r", capability="read_file", args=["true"])]

    return plan


def test_r0_action_auto_executes(tmp_path):
    gw, audit = _make_gateway(tmp_path, tmp_path)
    target = tmp_path / "data.txt"
    target.write_text("hello")
    loop = AgentLoop(gw, audit, _plan_reader(target))
    res = loop.run({})
    assert res.state == AgentState.DONE
    assert len(res.results) == 1
    assert res.results[0].success


def test_r3_action_blocked_without_approval(tmp_path):
    gw, audit = _make_gateway(tmp_path, tmp_path)
    tool = _write_tool(tmp_path)
    loop = AgentLoop(gw, audit, _plan_runner(tool))
    res = loop.run({}, approved_human=False)
    assert res.state == AgentState.AWAITING_HUMAN
    assert len(res.blocked) == 1
    assert len(res.results) == 0, "blocked action must not execute"


def test_r3_action_executes_with_approval(tmp_path):
    gw, audit = _make_gateway(tmp_path, tmp_path)
    tool = _write_tool(tmp_path)
    loop = AgentLoop(gw, audit, _plan_runner(tool))
    res = loop.run({}, approved_human=True)
    assert res.state == AgentState.DONE
    assert res.results[0].success


def test_gateway_cannot_be_bypassed(tmp_path):
    gw, audit = _make_gateway(tmp_path, tmp_path)
    called = {"n": 0}
    orig = gw.call

    def counting(req):
        called["n"] += 1
        return orig(req)

    gw.call = counting  # type: ignore[method-assign]
    loop = AgentLoop(gw, audit, _plan_true())
    loop.run({})
    assert called["n"] == 1


def test_audit_tamper_detected(tmp_path):
    gw, audit = _make_gateway(tmp_path, tmp_path)
    target = tmp_path / "d.txt"
    target.write_text("x")
    loop = AgentLoop(gw, audit, _plan_reader(target))
    res = loop.run({})
    assert res.state == AgentState.DONE
    recs = audit.records()
    assert len(recs) == 1
    recs[0].success = not recs[0].success  # tamper
    assert audit.verify() is False
