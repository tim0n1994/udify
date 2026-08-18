"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { mergeDisplayPreferences, serializeDisplayPreferences } from "./resolve";
import type {
  ConfigDiagnostic,
  ConfigResolution,
  Density,
  DisplayPreferences,
  JobTab,
} from "./schema";
import { displayPreferencesSchema } from "./schema";

export const DISPLAY_PREFERENCES_KEY = "udify.display.preferences";

interface ConfigContextValue extends ConfigResolution {
  setDensity: (density: Density) => void;
  setDefaultJobTab: (tab: JobTab) => void;
  resetPreferences: () => void;
}

const ConfigContext = createContext<ConfigContextValue | null>(null);

type StorageResult<T> = { ok: true; value: T } | { ok: false };

function browserStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function safeStorageRead(key: string): StorageResult<string | null> {
  try {
    const storage = browserStorage();
    return storage ? { ok: true, value: storage.getItem(key) } : { ok: false };
  } catch {
    return { ok: false };
  }
}

function safeStorageWrite(key: string, value: string): boolean {
  try {
    const storage = browserStorage();
    if (!storage) return false;
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function safeStorageRemove(key: string): boolean {
  try {
    const storage = browserStorage();
    if (!storage) return false;
    storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

function withStorageUnavailable(
  resolution: ConfigResolution,
  operation: "read" | "write" | "remove",
): ConfigResolution {
  const diagnostic: ConfigDiagnostic = {
    code: "CONFIG_LOCAL_UNAVAILABLE",
    source: "local-storage",
    message: `local display preferences could not be ${operation === "read" ? "read" : operation === "write" ? "saved" : "removed"}; using in-memory safe config`,
  };
  return {
    ...resolution,
    diagnostics: [
      ...resolution.diagnostics.filter((item) => item.code !== diagnostic.code),
      diagnostic,
    ],
  };
}

export function ConfigProvider({
  build,
  children,
}: {
  build: ConfigResolution;
  children: React.ReactNode;
}) {
  const [preferences, setPreferences] = useState<DisplayPreferences>({ version: 1 });
  const [resolution, setResolution] = useState(build);

  useEffect(() => {
    const read = safeStorageRead(DISPLAY_PREFERENCES_KEY);
    if (!read.ok) {
      setPreferences({ version: 1 });
      setResolution(withStorageUnavailable(build, "read"));
      return;
    }
    const raw = read.value;
    setResolution(mergeDisplayPreferences(build, raw));
    if (raw) {
      try {
        const parsed = displayPreferencesSchema.safeParse(JSON.parse(raw));
        if (parsed.success) setPreferences(parsed.data);
      } catch {
        setPreferences({ version: 1 });
      }
    }
  }, [build]);

  const update = useCallback((next: DisplayPreferences) => {
    setPreferences(next);
    const nextResolution = mergeDisplayPreferences(build, JSON.stringify(next));
    const saved = safeStorageWrite(
      DISPLAY_PREFERENCES_KEY,
      serializeDisplayPreferences(next),
    );
    setResolution(saved ? nextResolution : withStorageUnavailable(nextResolution, "write"));
  }, [build]);

  const value = useMemo<ConfigContextValue>(
    () => ({
      ...resolution,
      setDensity: (density) => update({ ...preferences, version: 1, density }),
      setDefaultJobTab: (defaultJobTab) =>
        update({ ...preferences, version: 1, defaultJobTab }),
      resetPreferences: () => {
        const removed = safeStorageRemove(DISPLAY_PREFERENCES_KEY);
        setPreferences({ version: 1 });
        setResolution(removed ? build : withStorageUnavailable(build, "remove"));
      },
    }),
    [build, preferences, resolution, update],
  );

  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig(): ConfigContextValue {
  const context = useContext(ConfigContext);
  if (!context) throw new Error("useConfig must be used within ConfigProvider");
  return context;
}
