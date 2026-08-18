import { DEFAULT_PUBLIC_CONFIG } from "@/config/defaults";
import {
  buildOverrideSchema,
  displayPreferencesSchema,
  publicConfigSchema,
  type ConfigDiagnostic,
  type ConfigResolution,
  type DisplayPreferences,
  type PublicConfig,
} from "./schema";

function mergeBuildOverride(base: PublicConfig, override: unknown): PublicConfig {
  const value = override as Partial<PublicConfig>;
  return {
    ...base,
    ...value,
    brand: value.brand ?? base.brand,
    navigation: value.navigation ?? base.navigation,
    features: value.features ?? base.features,
    polling: value.polling ?? base.polling,
    apiBase: base.apiBase,
  };
}

export function resolveBuildConfig(
  publicConfigJson?: string,
  apiBaseOverride?: string,
): ConfigResolution {
  const diagnostics: ConfigDiagnostic[] = [];
  let resolved = DEFAULT_PUBLIC_CONFIG;

  if (publicConfigJson) {
    try {
      const parsed = buildOverrideSchema.safeParse(JSON.parse(publicConfigJson));
      if (parsed.success) {
        resolved = mergeBuildOverride(resolved, parsed.data);
      } else {
        diagnostics.push({
          code: "CONFIG_ENV_INVALID",
          source: "public-env",
          message: parsed.error.issues[0]?.message ?? "invalid public config",
        });
      }
    } catch {
      diagnostics.push({
        code: "CONFIG_ENV_INVALID",
        source: "public-env",
        message: "NEXT_PUBLIC_UDIFY_CONFIG must be valid JSON",
      });
    }
  }

  if (apiBaseOverride) {
    const candidate = publicConfigSchema.safeParse({ ...resolved, apiBase: apiBaseOverride });
    if (candidate.success) {
      resolved = candidate.data;
    } else {
      diagnostics.push({
        code: "CONFIG_API_INVALID",
        source: "api-env",
        message: candidate.error.issues[0]?.message ?? "invalid API base",
      });
    }
  }

  const final = publicConfigSchema.safeParse(resolved);
  return {
    config: final.success ? final.data : DEFAULT_PUBLIC_CONFIG,
    diagnostics,
  };
}

export function mergeDisplayPreferences(
  build: ConfigResolution,
  raw: string | null,
): ConfigResolution {
  if (!raw) return build;
  try {
    const parsed = displayPreferencesSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) throw parsed.error;
    return {
      config: {
        ...build.config,
        density: parsed.data.density ?? build.config.density,
        defaultJobTab: parsed.data.defaultJobTab ?? build.config.defaultJobTab,
      },
      diagnostics: build.diagnostics,
    };
  } catch {
    return {
      config: build.config,
      diagnostics: [
        ...build.diagnostics,
        {
          code: "CONFIG_LOCAL_INVALID",
          source: "local-storage",
          message: "display preferences were ignored; reset to safe defaults",
        },
      ],
    };
  }
}

export function serializeDisplayPreferences(preferences: DisplayPreferences): string {
  return JSON.stringify(displayPreferencesSchema.parse(preferences));
}
