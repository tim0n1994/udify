"use client";

import { Grid } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import type { Group } from "three";
import type { Job } from "@/lib/api";

interface PrismSource {
  events: number;
  validHue: boolean;
  confidence: number;
}

function Pylon({ source }: { source: PrismSource }) {
  const group = useRef<Group>(null);
  useFrame(({ clock }) => {
    if (group.current) {
      group.current.rotation.y = clock.elapsedTime * 0.35;
      group.current.position.y = Math.sin(clock.elapsedTime * 1.1) * 0.22;
    }
  });
  return (
    <group ref={group}>
      <mesh>
        <cylinderGeometry args={[0.65, 0.85, 2.6 + source.events * 0.06, 3, 1]} />
        <meshStandardMaterial
          color={source.validHue ? "#9a6410" : "#7e3032"}
          emissive={source.validHue ? "#4d3206" : "#3c1819"}
          emissiveIntensity={0.8}
          metalness={0.55}
          roughness={0.4}
          flatShading
        />
      </mesh>
    </group>
  );
}

/** WebGL 证据场：MIU2D 水域 Caustics + 审计 pylons；2b 密度采样 asset field。 */
export function PrismField({
  jobs,
  selected,
}: {
  jobs: Job[];
  selected: { events: number; valid: boolean } | null;
}) {
  const pylons = useMemo<PrismSource[]>(
    () =>
      jobs.slice(0, 9).map((job, index) => ({
        events: Object.keys(job.checkpoint).length + (index % 3),
        validHue: job.status !== "failed",
        confidence: 1,
      })),
    [jobs],
  );
  const selectedSource: PrismSource = {
    events: selected?.events ?? 3,
    validHue: selected?.valid !== false,
    confidence: 1,
  };
  return (
    <Canvas
      camera={{ position: [2.6, 2.1, 3.2], fov: 46 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true, powerPreference: "low-power", preserveDrawingBuffer: true }}
      style={{ width: "100%", height: "100%", display: "block" }}
      aria-hidden
    >
      <color attach="background" args={["#05070a"]} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 7, 3]} intensity={2.4} color="#ffe0b0" />
      <pointLight position={[0, 2.4, 0]} intensity={20} color="#f6a51a" distance={8} decay={2} />
      <pointLight position={[-3, 0.8, -3]} intensity={5} color="#f6d17a" distance={10} decay={2} />
      {/* 地面：承载 drei Grid；避免 plane 同面深度写入互踩，垫低 0.01 并始建不为 Grid 所覆。 */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.36, 0]}>
        <planeGeometry args={[14, 14]} />
        <meshStandardMaterial color="#241a10" roughness={0.7} metalness={0.3} />
      </mesh>
      <Pylon source={selectedSource} />
      {pylons.slice(1, 5).map((p, i) => (
        <group key={i} position={[Math.cos(i * 1.6 + 0.7) * 2.6, -0.5, Math.sin(i * 1.6 + 0.7) * 2.6]}>
          <mesh>
            <cylinderGeometry args={[0.22, 0.3, 0.9 + p.events * 0.1, 3]} />
            <meshStandardMaterial
              color={p.validHue ? "#f6d17a" : "#f28b89"}
              emissive={p.validHue ? "#a87c1c" : "#a83230"}
              emissiveIntensity={1.0}
              flatShading
            />
          </mesh>
        </group>
      ))}
      <Grid
        args={[10, 10]}
        cellColor="#2d3742"
        sectionColor="#4a5663"
        sectionThickness={1.1}
        cellThickness={0.6}
        fadeDistance={14}
        position={[0, -1.25, 0]}
      />
    </Canvas>
  );
}
