'use client';

/**
 * Avatar3d — the AI tutor rendered as a live 3D head (Ready Player Me .glb).
 *
 * Browser-only richer version of the tutor orb: it auto-frames any rig to a
 * head-and-shoulders portrait, blinks, gently sways, and moves its mouth while
 * Numera is speaking. No external audio analyser — the mouth is driven by the
 * `speaking` flag (from voiceStatus) with a layered-sine pseudo lip-sync, so it
 * reads as alive without a voice-data dependency. On any load error the parent
 * keeps its orb fallback (see TutorTile).
 */

import { Canvas, useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { Suspense, useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useMicLevel } from '@/store/useMicLevel';

const MODEL_URL = '/models/tutor.glb';

type MorphMap = Map<string, { mesh: THREE.Mesh; idx: number }[]>;

/** Index every morph target so expressions can be driven by name. */
function indexMorphs(scene: THREE.Object3D): MorphMap {
  const map: MorphMap = new Map();
  scene.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh && m.morphTargetDictionary && m.morphTargetInfluences) {
      for (const [name, idx] of Object.entries(m.morphTargetDictionary)) {
        const list = map.get(name) ?? [];
        list.push({ mesh: m, idx });
        map.set(name, list);
      }
    }
  });
  return map;
}

function Avatar({ onReady }: { onReady?: () => void }) {
  const { scene } = useGLTF(MODEL_URL);
  const group = useRef<THREE.Group>(null);
  const jaw = useRef(0);
  const blink = useRef({ playing: -1, next: 1.5 });
  const morphs = useMemo(() => indexMorphs(scene), [scene]);

  // useGLTF suspends until the model is decoded, so by here it's ready.
  useEffect(() => { onReady?.(); }, [onReady]);

  // Normalise any rig to the same head-and-shoulders portrait: fixed height,
  // centred horizontally, crown just inside the top of the frame.
  const fit = useMemo(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const size = box.getSize(new THREE.Vector3());
    const c = box.getCenter(new THREE.Vector3());
    const s = size.y > 0.001 ? 1.7 / size.y : 1;
    return { s, px: -c.x * s, py: 0.12 - box.max.y * s };
  }, [scene]);

  const setMorph = (name: string, v: number) => {
    const targets = morphs.get(name);
    if (!targets) return;
    for (const { mesh, idx } of targets) {
      if (mesh.morphTargetInfluences) mesh.morphTargetInfluences[idx] = v;
    }
  };

  useFrame((state, dt) => {
    const k = Math.min(1, dt * 18); // frame-rate-independent smoothing
    const t = state.clock.elapsedTime;

    // Mouth: driven by Numera's live TTS (read imperatively — no re-render).
    // Each spoken-word boundary opens the mouth (decaying), with a light flutter
    // between words so the lips keep moving through the whole utterance.
    const { aiSpeaking, lastBoundary } = useMicLevel.getState();
    let level = 0;
    if (aiSpeaking) {
      const sinceWord = (performance.now() - lastBoundary) / 1000;
      const wordEnv = Math.exp(-Math.max(0, sinceWord) * 7);
      const flutter = 0.35 + 0.35 * Math.sin(t * 20);
      level = Math.min(1, 0.4 * flutter + 0.7 * wordEnv);
    }
    jaw.current += (level - jaw.current) * k;
    setMorph('jawOpen', jaw.current * 0.62);
    setMorph('viseme_aa', jaw.current * 0.4);

    // Periodic blink.
    const bl = blink.current;
    if (bl.playing < 0 && t > bl.next) bl.playing = 0;
    if (bl.playing >= 0) {
      bl.playing += dt;
      const p = bl.playing / 0.16;
      const v = p < 0.5 ? p * 2 : Math.max(0, 2 - 2 * p);
      setMorph('eyeBlinkLeft', v);
      setMorph('eyeBlinkRight', v);
      if (bl.playing > 0.16) {
        bl.playing = -1;
        bl.next = t + 2.5 + Math.random() * 3.5;
      }
    }

    // Subtle idle head sway so the face never looks frozen.
    if (group.current) {
      group.current.rotation.y = Math.sin(t * 0.5) * 0.05;
      group.current.rotation.x = Math.sin(t * 0.7) * 0.02;
    }
  });

  return (
    <group ref={group} scale={fit.s} position={[fit.px, fit.py, 0]}>
      <primitive object={scene} />
    </group>
  );
}

export default function Avatar3d({ onReady }: { onReady?: () => void }) {
  return (
    <Canvas
      gl={{ alpha: true, antialias: true }}
      camera={{ position: [0, 0, 1.05], fov: 26 }}
      style={{ background: 'transparent' }}
      dpr={[1, 2]}
    >
      <ambientLight intensity={0.95} />
      <directionalLight position={[1, 2, 3]} intensity={1.25} />
      <directionalLight position={[-2, 1, 1]} intensity={0.4} />
      {/* Numera cyan rim light */}
      <directionalLight position={[0, 1, -2]} intensity={0.7} color="#00B4D8" />
      <Suspense fallback={null}>
        <Avatar onReady={onReady} />
      </Suspense>
    </Canvas>
  );
}

useGLTF.preload(MODEL_URL);
