import type { Job, JobDetail, Plan, Report } from "@/lib/api";

const now = 1_753_776_000;

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    job_id: "job-review-001",
    game_root: "/games/miu2d-demo",
    intent: "让第一个 Boss 更难，但不要单纯翻倍血量",
    status: "awaiting_review",
    created_at: now,
    updated_at: now + 12,
    artifacts_dir: "/state/jobs/job-review-001",
    error: null,
    checkpoint: { graph_checksum: "abc123456789def", operations: 2 },
    ...overrides,
  };
}

export const jobsFixture: Job[] = [
  makeJob(),
  makeJob({ job_id: "job-active-002", intent: "调整新手区治疗资源", status: "validating" }),
  makeJob({ job_id: "job-done-003", intent: "修复 NPC 奖励配置", status: "completed" }),
  makeJob({
    job_id: "job-failed-004",
    intent: "修改危险 Lua 脚本",
    status: "failed",
    error: {
      code: "JOB_VALIDATION_BLOCKED",
      message: "静态验证发现危险 API",
      owner_module: "validation",
      retryable: false,
      suggested_action: "调整意图后重新创建任务",
    },
  }),
  makeJob({ job_id: "job-rolled-005", intent: "回滚敌人血量修改", status: "rolled_back" }),
];

export const detailFixture: JobDetail = {
  job: jobsFixture[0]!,
  audit_chain_valid: true,
  events: [
    { job_id: "job-review-001", seq: 1, ts: now, stage: "created", event: "job_created", payload: {}, record_hash: "h1" },
    { job_id: "job-review-001", seq: 2, ts: now + 4, stage: "perceiving", event: "stage_started", payload: {}, record_hash: "h2" },
    { job_id: "job-review-001", seq: 3, ts: now + 12, stage: "awaiting_review", event: "review_requested", payload: {}, record_hash: "h3" },
  ],
};

export const planFixture: Plan = {
  intent: detailFixture.job.intent,
  graph_checksum: "abc123456789def",
  actions: [],
  operations: [
    {
      op_type: "modify_property",
      target_id: "Boss_01",
      execution_mode: "file_patch",
      payload: { property: "max_hp", old_value: 50000, value: 72000 },
      source_span: { file_path: "config/enemy.ini", line_start: 2, line_end: 3 },
      risk: 0.45,
      planning_reason: "提升生存压力，但避免简单翻倍",
    },
    {
      op_type: "modify_property",
      target_id: "Boss_01",
      execution_mode: "file_patch",
      payload: { property: "attack", old_value: 320, value: 360 },
      source_span: { file_path: "config/enemy.ini", line_start: 3, line_end: 3 },
      risk: 0.3,
      planning_reason: "小幅提升攻击压力",
    },
  ],
  diffs: [
    {
      path: "config/enemy.ini",
      status: "modified",
      original: "[Boss_01]\nmax_hp=50000\nattack=320\ndefense=120\n",
      current: "[Boss_01]\nmax_hp=72000\nattack=360\ndefense=120\n",
    },
  ],
  op_errors: [],
  static_validation: {
    passed: true,
    blocking_errors: [],
    warnings: [],
    confidence: 0.98,
    recommended_action: "approve",
    error_count: 0,
    warning_count: 0,
  },
};

export const reportFixture: Report = {
  static_validation: planFixture.static_validation,
  probe: {
    passed: true,
    game_started: true,
    state_readable: true,
    console_error_count: 0,
    probe_count: 1,
    results: [{ probe_id: "boot", passed: true, kind: "headless", observed: {}, console_errors: [], evidence: "boot ok" }],
  },
  graph_checksum_before: "abc123456789def",
  graph_checksum_applied_on: "abc123456789def",
};

export function ok<T>(data: T) {
  return { success: true, data, error: null, meta: null };
}
