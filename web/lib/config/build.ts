import { resolveBuildConfig } from "./resolve";

/** Direct env reads are required for Next.js public build-time substitution. */
export const BUILD_CONFIG = resolveBuildConfig(
  process.env.NEXT_PUBLIC_UDIFY_CONFIG,
  process.env.NEXT_PUBLIC_UDIFY_API,
);
