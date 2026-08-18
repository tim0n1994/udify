"""
LLM 三级预算护栏（iter4 M2，T2-LLM-OBS-COST 研究落地）。

三级预算：全局 / 每日 / 每 job。reserve-then-settle 模式：
- reserve：调用前预占（检查三级预算是否允许）。
- settle：调用后回填真实 token（预占转化为实际）。
- release：调用失败时释放预占。

并发安全：单用户但 JobRunner 后台线程跑多 job。用 threading.Lock 保护内存计数；
若要跨进程持久化，可序列化到 sqlite（本轮预留接口，不强制）。

设计原则：
- fail-closed：超预算硬停，不静默降级（降级由调用方根据 ReservationResult 决定）。
- 防 runaway：单 job 超预算（max_tokens 或 max_calls）硬停。
- 无 key 时不会被调用（调用方先检查）。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum

from udify.core.cognition.intent_trace import TokenUsageTrace


class BudgetScope(StrEnum):
    GLOBAL = "global"
    DAILY = "daily"
    JOB = "job"


class BudgetDecision(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED_GLOBAL = "DENIED_GLOBAL"
    DENIED_DAILY = "DENIED_DAILY"
    DENIED_JOB = "DENIED_JOB"


@dataclass(frozen=True, slots=True)
class BudgetLimit:
    """一个 scope 的预算上限。"""

    max_tokens: int = 0  # 0 = 不限制
    max_calls: int = 0

    def allows(self, used_tokens: int, used_calls: int) -> bool:
        # A limit of N permits up to N (inclusive). used_* here is the count
        # AFTER the prospective reservation, so permit iff it does not EXCEED.
        tok_ok = not (self.max_tokens and used_tokens > self.max_tokens)
        call_ok = not (self.max_calls and used_calls > self.max_calls)
        return tok_ok and call_ok


@dataclass(frozen=True, slots=True)
class BudgetDenied:
    """预算被拒的原因。"""

    scope: BudgetScope
    limit: BudgetLimit
    used_tokens: int
    used_calls: int


@dataclass
class ReservationRequest:
    """调用前预占请求。"""

    job_id: str
    estimated_tokens: int
    day_key: str = ""  # YYYY-MM-DD，空则用今天


@dataclass(frozen=True, slots=True)
class ReservationResult:
    """预占结果。"""

    allowed: bool
    reservation_id: str
    decision: BudgetDecision
    denied: BudgetDenied | None = None


@dataclass
class _ScopeState:
    """单 scope 的运行时计数（可变，受锁保护）。"""

    used_tokens: int = 0
    used_calls: int = 0
    # pending 预占（reservation_id -> tokens），settle 时扣除。
    pending: dict[str, int] = field(default_factory=dict)


@dataclass
class LLMBudgetPolicy:
    """三级预算策略（全局/每日/job）。

    线程安全：所有 reserve/settle/release 操作持 _lock。
    """

    global_limit: BudgetLimit = field(
        default_factory=lambda: BudgetLimit(max_tokens=1_000_000, max_calls=500)
    )
    daily_limit: BudgetLimit = field(
        default_factory=lambda: BudgetLimit(max_tokens=100_000, max_calls=50)
    )
    job_limit: BudgetLimit = field(
        default_factory=lambda: BudgetLimit(max_tokens=8000, max_calls=2)
    )

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._global = _ScopeState()
        self._daily: dict[str, _ScopeState] = {}
        self._jobs: dict[str, _ScopeState] = {}
        self._next_id = 0

    def _day(self, req: ReservationRequest) -> str:
        return req.day_key or _today()

    def reserve(self, req: ReservationRequest) -> ReservationResult:
        """预占预算（调用前）。三级检查，任一拒绝即拒绝。"""
        with self._lock:
            day = self._day(req)
            day_state = self._daily.setdefault(day, _ScopeState())
            job_state = self._jobs.setdefault(req.job_id, _ScopeState())
            # 含 pending 的有效计数
            g_tok = self._global.used_tokens + req.estimated_tokens
            g_cal = self._global.used_calls + 1
            d_tok = day_state.used_tokens + req.estimated_tokens
            d_cal = day_state.used_calls + 1
            j_tok = job_state.used_tokens + req.estimated_tokens
            j_cal = job_state.used_calls + 1
            if not self.global_limit.allows(self._global.used_tokens, self._global.used_calls):
                return self._deny(req, BudgetScope.GLOBAL, BudgetDecision.DENIED_GLOBAL)
            if not self.global_limit.allows(g_tok, g_cal):
                return self._deny(req, BudgetScope.GLOBAL, BudgetDecision.DENIED_GLOBAL)
            if not self.daily_limit.allows(day_state.used_tokens, day_state.used_calls):
                return self._deny(req, BudgetScope.DAILY, BudgetDecision.DENIED_DAILY)
            if not self.daily_limit.allows(d_tok, d_cal):
                return self._deny(req, BudgetScope.DAILY, BudgetDecision.DENIED_DAILY)
            if not self.job_limit.allows(job_state.used_tokens, job_state.used_calls):
                return self._deny(req, BudgetScope.JOB, BudgetDecision.DENIED_JOB)
            if not self.job_limit.allows(j_tok, j_cal):
                return self._deny(req, BudgetScope.JOB, BudgetDecision.DENIED_JOB)
            # 通过：记录 pending
            self._next_id += 1
            rid = f"{req.job_id}-{self._next_id}"
            self._global.pending[rid] = req.estimated_tokens
            day_state.pending[rid] = req.estimated_tokens
            job_state.pending[rid] = req.estimated_tokens
            return ReservationResult(
                allowed=True, reservation_id=rid, decision=BudgetDecision.ALLOWED
            )

    def _deny(
        self, req: ReservationRequest, scope: BudgetScope, decision: BudgetDecision
    ) -> ReservationResult:
        limit = {
            BudgetScope.GLOBAL: self.global_limit,
            BudgetScope.DAILY: self.daily_limit,
            BudgetScope.JOB: self.job_limit,
        }[scope]
        return ReservationResult(
            allowed=False,
            reservation_id="",
            decision=decision,
            denied=BudgetDenied(
                scope=scope, limit=limit, used_tokens=req.estimated_tokens, used_calls=1
            ),
        )

    def settle(self, reservation_id: str, actual: TokenUsageTrace) -> None:
        """调用后回填真实 token（pending -> actual）。

        settlement 在所有 scope 上把预占转化为实际用量：清 pending，累加真实 token/call。
        reservation_id 形如 "<job_id>-<n>"，据此定位 job；daily 用当天 key。
        """
        with self._lock:
            actual_tokens = actual.total_tokens
            self._global.pending.pop(reservation_id, None)
            self._global.used_tokens += actual_tokens
            self._global.used_calls += 1
            for state in list(self._daily.values()) + list(self._jobs.values()):
                if state.pending.pop(reservation_id, None) is not None:
                    state.used_tokens += actual_tokens
                    state.used_calls += 1

    def release(self, reservation_id: str) -> None:
        """调用失败时释放预占（不累加）。"""
        with self._lock:
            self._global.pending.pop(reservation_id, None)
            for state in list(self._daily.values()) + list(self._jobs.values()):
                state.pending.pop(reservation_id, None)

    def job_usage(self, job_id: str) -> TokenUsageTrace:
        """查询单 job 累计用量（不含 pending）。"""
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return TokenUsageTrace()
            return TokenUsageTrace(input_tokens=state.used_tokens)


def _today() -> str:
    from datetime import date

    return date.today().isoformat()
