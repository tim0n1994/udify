import type { z } from "zod";
import type {
  errorRecordSchema,
  fileDiffSchema,
  jobDetailSchema,
  jobEventSchema,
  jobSchema,
  jobStatusSchema,
  modsDataSchema,
  patchOpSchema,
  planSchema,
  reportSchema,
  sourceSpanSchema,
  staticValidationSchema,
} from "./schema";

export type ErrorRecord = z.infer<typeof errorRecordSchema>;
export type JobStatus = z.infer<typeof jobStatusSchema>;
export type Job = z.infer<typeof jobSchema>;
export type JobEvent = z.infer<typeof jobEventSchema>;
export type JobDetail = z.infer<typeof jobDetailSchema>;
export type SourceSpan = z.infer<typeof sourceSpanSchema>;
export type PatchOp = z.infer<typeof patchOpSchema>;
export type FileDiff = z.infer<typeof fileDiffSchema>;
export type StaticValidation = z.infer<typeof staticValidationSchema>;
export type Plan = z.infer<typeof planSchema>;
export type Report = z.infer<typeof reportSchema>;
export type ModsData = z.infer<typeof modsDataSchema>;
