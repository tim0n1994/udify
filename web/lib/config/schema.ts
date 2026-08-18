import { z } from "zod";

export const jobTabSchema = z.enum(["changes", "risk", "report"]);
export type JobTab = z.infer<typeof jobTabSchema>;

export const densitySchema = z.enum(["comfortable", "compact"]);
export type Density = z.infer<typeof densitySchema>;

const loopbackUrlSchema = z.string().url().superRefine((value, context) => {
  const parsed = new URL(value);
  if (parsed.protocol !== "http:") {
    context.addIssue({ code: "custom", message: "API URL must use http" });
  }
  if (!new Set(["127.0.0.1", "localhost"]).has(parsed.hostname)) {
    context.addIssue({ code: "custom", message: "API URL must target loopback" });
  }
  if (parsed.username || parsed.password) {
    context.addIssue({ code: "custom", message: "API URL must not include credentials" });
  }
  if (parsed.pathname !== "/") {
    context.addIssue({ code: "custom", message: "API URL must not include a path" });
  }
  if (parsed.search) {
    context.addIssue({ code: "custom", message: "API URL must not include a query" });
  }
  if (parsed.hash) {
    context.addIssue({ code: "custom", message: "API URL must not include a fragment" });
  }
});

const publicConfigObjectSchema = z
  .object({
    version: z.literal(1),
    brand: z
      .object({
        name: z.string().trim().min(1).max(24),
        product: z.string().trim().min(1).max(40),
      })
      .strict(),
    navigation: z
      .array(
        z
          .object({
            id: z.enum(["tasks", "mods", "system"]),
            label: z.string().trim().min(1).max(24),
            href: z.literal("/"),
            enabled: z.boolean(),
          })
          .strict(),
      )
      .min(1)
      .max(3),
    features: z
      .object({
        showJobInspector: z.boolean(),
        showConfigDiagnostics: z.boolean(),
      })
      .strict(),
    polling: z
      .object({
        activeMs: z.number().int().min(500).max(30_000),
        idleMs: z.number().int().min(2_000).max(120_000),
        healthMs: z.number().int().min(2_000).max(120_000),
      })
      .strict(),
    density: densitySchema,
    defaultJobTab: jobTabSchema,
    apiBase: loopbackUrlSchema,
  })
  .strict();

export const publicConfigSchema = publicConfigObjectSchema.superRefine((config, context) => {
  config.navigation.forEach((item, index) => {
    if (item.id !== "tasks" && item.enabled) {
      context.addIssue({
        code: "custom",
        path: ["navigation", index, "enabled"],
        message: `${item.id} has no product route in this release`,
      });
    }
  });
});

export type PublicConfig = z.infer<typeof publicConfigSchema>;

export const buildOverrideSchema = publicConfigObjectSchema
  .omit({ apiBase: true })
  .partial()
  .extend({ version: z.literal(1) })
  .strict();

export const displayPreferencesSchema = z
  .object({
    version: z.literal(1),
    density: densitySchema.optional(),
    defaultJobTab: jobTabSchema.optional(),
  })
  .strict();

export type DisplayPreferences = z.infer<typeof displayPreferencesSchema>;

export interface ConfigDiagnostic {
  code:
    | "CONFIG_ENV_INVALID"
    | "CONFIG_API_INVALID"
    | "CONFIG_LOCAL_INVALID"
    | "CONFIG_LOCAL_UNAVAILABLE";
  source: "public-env" | "api-env" | "local-storage";
  message: string;
}

export interface ConfigResolution {
  config: PublicConfig;
  diagnostics: ConfigDiagnostic[];
}
