import { z } from "zod";

const unknownRecord = z.record(z.string(), z.unknown());

export const errorRecordSchema = z.object({
  code: z.string(),
  message: z.string(),
  owner_module: z.string(),
  retryable: z.boolean(),
  suggested_action: z.string(),
});

export const jobStatusSchema = z.enum([
  "created",
  "perceiving",
  "planning",
  "awaiting_clarification",
  "awaiting_review",
  "applying",
  "validating",
  "packaging",
  "completed",
  "failed",
  "compensating",
  "rolled_back",
  "rejected",
]);

export const jobSchema = z.object({
  job_id: z.string(),
  game_root: z.string(),
  intent: z.string(),
  status: jobStatusSchema,
  created_at: z.number(),
  updated_at: z.number(),
  artifacts_dir: z.string(),
  error: errorRecordSchema.nullable(),
  checkpoint: unknownRecord,
});

export const jobEventSchema = z.object({
  job_id: z.string(),
  seq: z.number().int(),
  ts: z.number(),
  stage: z.string(),
  event: z.string(),
  payload: unknownRecord,
  prev_hash: z.string().optional(),
  record_hash: z.string(),
});

export const jobDetailSchema = z.object({
  job: jobSchema,
  events: z.array(jobEventSchema),
  audit_chain_valid: z.boolean(),
});

export const sourceSpanSchema = z.object({
  file_path: z.string(),
  line_start: z.number().int().nullable(),
  line_end: z.number().int().nullable(),
});

export const patchOpSchema = z.object({
  op_type: z.string(),
  target_id: z.string(),
  payload: unknownRecord,
  execution_mode: z.string().optional(),
  source_span: sourceSpanSchema.optional(),
  risk: z.number().optional(),
  planning_reason: z.string().optional(),
});

export const fileDiffSchema = z.object({
  path: z.string(),
  status: z.enum(["modified", "new", "deleted"]),
  original: z.string().nullable(),
  current: z.string().nullable(),
  diff: z
    .array(z.object({ type: z.enum(["add", "remove"]), line: z.string() }))
    .optional(),
});

export const validationFindingSchema = z.object({
  check: z.string(),
  severity: z.string(),
  message: z.string(),
  target_id: z.string(),
  evidence: unknownRecord,
});

export const staticValidationSchema = z.object({
  passed: z.boolean(),
  blocking_errors: z.array(validationFindingSchema),
  warnings: z.array(validationFindingSchema),
  confidence: z.number(),
  recommended_action: z.string(),
  error_count: z.number().int(),
  warning_count: z.number().int(),
});

export const planSchema = z.object({
  intent: z.string(),
  graph_checksum: z.string(),
  actions: z.array(
    z.object({
      schema: z.string(),
      target: z.string(),
      params: unknownRecord,
      reason: z.string(),
    }),
  ),
  operations: z.array(patchOpSchema),
  diffs: z.array(fileDiffSchema),
  op_errors: z.array(z.string()),
  static_validation: staticValidationSchema,
});

export const probeResultSchema = z.object({
  probe_id: z.string(),
  passed: z.boolean(),
  kind: z.string(),
  observed: unknownRecord,
  console_errors: z.array(z.string()),
  evidence: z.string(),
});

export const reportSchema = z.object({
  engine_coverage: z.string().optional(),
  delivery: z.object({
    kind: z.literal("package"),
    installed: z.literal(false),
    tier: z.enum(["STATIC_ONLY", "UNVERIFIED_ARTIFACT", "VERIFIED_ARTIFACT"]),
    reason: z.string(),
  }).optional(),
  artifact_validation: z.object({
    passed: z.boolean(),
    checks: z.array(z.object({ name: z.string(), passed: z.boolean(), detail: z.string() })),
  }).optional(),
  artifacts: z.array(z.object({ name: z.string(), sha256: z.string() })).optional(),
  approval: z.object({
    plan_sha256: z.string(),
    patch_sha256: z.string(),
    source_files: z.array(z.object({ name: z.string(), sha256: z.string() })),
  }).optional(),
  gate_verdict: z.object({
    final_tier: z.number(),
    final_tier_reason: z.string(),
    gates: z.array(z.object({
      name: z.string(), lifecycle: z.string(), verdict: z.string(),
      evidence: z.unknown(), delivery_tier: z.number(),
    })),
  }).optional(),
  static_validation: staticValidationSchema,
  probe: z.object({
    skipped: z.boolean().optional(),
    reason: z.string().optional(),
    passed: z.boolean(),
    game_started: z.boolean(),
    state_readable: z.boolean(),
    console_error_count: z.number().int(),
    probe_count: z.number().int(),
    results: z.array(probeResultSchema),
  }),
  graph_checksum_before: z.string().nullable(),
  graph_checksum_applied_on: z.string(),
});

export const clarificationSchema = z.object({
  question: z.string(),
  candidates: z.array(z.object({ node_id: z.string().min(1), display_name: z.string() })),
  reason: z.string(),
  graph_checksum: z.string(),
});

export const rollbackEvidenceSchema = z.object({
  checksum_intact: z.boolean().nullable(),
  source_integrity_reason: z.string(),
  package_revoked: z.string().nullable(),
});

export const healthSchema = z.object({
  version: z.string(),
  engines: z.record(z.string(), z.boolean()),
});

export const modsDataSchema = z.object({
  mods: z.array(
    z.object({
      job_id: z.string(),
      intent: z.string(),
      package: z.string().nullable(),
      operations: z.number().int(),
      created_at: z.number(),
    }),
  ),
  conflicts: z.array(
    z.object({ job_a: z.string(), job_b: z.string(), shared_targets: z.array(z.string()) }),
  ),
});

export const envelopeSchema = z.object({
  success: z.boolean(),
  data: z.unknown(),
  error: errorRecordSchema.nullable(),
  meta: unknownRecord.nullable(),
});
