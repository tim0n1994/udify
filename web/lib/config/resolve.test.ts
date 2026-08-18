import { DEFAULT_PUBLIC_CONFIG } from "@/config/defaults";
import { mergeDisplayPreferences, resolveBuildConfig } from "./resolve";

describe("frontend config contract", () => {
  it("merges a checked versioned build override", () => {
    const result = resolveBuildConfig(JSON.stringify({ version: 1, density: "compact" }));
    expect(result.config.density).toBe("compact");
    expect(result.config.brand).toEqual(DEFAULT_PUBLIC_CONFIG.brand);
    expect(result.diagnostics).toEqual([]);
  });

  it("falls back without blanking on malformed env JSON", () => {
    const result = resolveBuildConfig("{bad");
    expect(result.config).toEqual(DEFAULT_PUBLIC_CONFIG);
    expect(result.diagnostics[0]?.code).toBe("CONFIG_ENV_INVALID");
  });

  it.each(["http://localhost:8765", "http://127.0.0.1", "http://127.0.0.1:9000/"])(
    "accepts a root loopback API override: %s",
    (apiBase) => {
      const result = resolveBuildConfig(undefined, apiBase);
      expect(result.config.apiBase).toBe(apiBase);
      expect(result.diagnostics).toEqual([]);
    },
  );

  it.each([
    "http://user:pass@localhost:8765",
    "http://localhost:8765/foo",
    "http://localhost:8765?x=1",
    "http://localhost:8765#fragment",
    "https://localhost:8765",
    "http://example.com:8765",
  ])("rejects an unsafe or non-root API override: %s", (apiBase) => {
    const result = resolveBuildConfig(undefined, apiBase);
    expect(result.config.apiBase).toBe(DEFAULT_PUBLIC_CONFIG.apiBase);
    expect(result.diagnostics[0]?.code).toBe("CONFIG_API_INVALID");
  });

  it("ignores old or corrupted local preferences and keeps build config", () => {
    const build = resolveBuildConfig(JSON.stringify({ version: 1, density: "compact" }));
    const old = mergeDisplayPreferences(build, JSON.stringify({ version: 0, density: "comfortable" }));
    expect(old.config.density).toBe("compact");
    expect(old.diagnostics.at(-1)?.code).toBe("CONFIG_LOCAL_INVALID");
  });
});
