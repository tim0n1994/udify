"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ActionTone = "approve" | "reject" | "create" | "fail";

interface SoundContextValue {
  enabled: boolean;
  toggle: () => void;
  play: (tone: ActionTone) => void;
}

const SoundContext = createContext<SoundContextValue | null>(null);
const STORAGE_KEY = "udify:sound-enabled";

interface Synth {
  triggerAttackRelease: (note: string, duration: string, time?: number) => void;
  dispose: () => void;
}

/** 意图动作音效：Tone.js 惰性加载，-18dB ceiling，三次短促音符合操作员确认感。 */
export function SoundProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(false);
  const synthRef = useRef<Synth | null>(null);
  const loadingRef = useRef<Promise<Synth> | null>(null);

  useEffect(() => {
    try {
      setEnabled(window.localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      // 隐私模式下 localStorage 不可用；保持默认静音
    }
  }, []);

  const ensureSynth = useCallback((): Promise<Synth> => {
    if (synthRef.current) return Promise.resolve(synthRef.current);
    if (!loadingRef.current) {
      loadingRef.current = import("tone").then((Tone) => {
        const limiter = new Tone.Limiter(-18).toDestination();
        const synth = new Tone.MembraneSynth({
          volume: -10,
          envelope: { attack: 0.001, decay: 0.28, sustain: 0, release: 0.1 },
        }).connect(limiter);
        synthRef.current = synth as unknown as Synth;
        return synthRef.current;
      });
    }
    return loadingRef.current;
  }, []);

  const play = useCallback(
    (tone: ActionTone) => {
      if (!enabled) return;
      const notes: Record<ActionTone, [string, string]> = {
        create: ["C3", "16n"],
        approve: ["E3", "8n"],
        reject: ["G2", "8n"],
        fail: ["A1", "4n"],
      };
      void ensureSynth().then((synth) => {
        const [note, duration] = notes[tone];
        synth.triggerAttackRelease(note, duration);
      });
    },
    [enabled, ensureSynth],
  );

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* in-memory only */
      }
      return next;
    });
  }, []);

  const value = useMemo(() => ({ enabled, toggle, play }), [enabled, toggle, play]);
  return <SoundContext.Provider value={value}>{children}</SoundContext.Provider>;
}

export function useSound(): SoundContextValue {
  const context = useContext(SoundContext);
  if (!context) throw new Error("useSound must be used within SoundProvider");
  return context;
}
