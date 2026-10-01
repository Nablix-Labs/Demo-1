'use client';

/**
 * CONNECT arrows from the canvas teaching plan.
 *
 * Question tokens are HTML while tutor notes live in the drawing stage. Token
 * links use drawably; source-to-note links use a viewport SVG so they cross
 * those two surfaces without inventing coordinates on the server.
 */

import { useEffect, useLayoutEffect, useState } from 'react';
import { drawablyArrow } from 'drawably';
import 'drawably/style.css';
import { TEACHING_COLORS, type SceneTeachingConnector } from '@/lib/canvasTeachingPlan';
import { useNumeraStore, type TutorElement } from '@/store/useNumeraStore';
import { useTutorReveal } from '@/store/useTutorReveal';

/** Below this centre-to-centre distance an arrow is too short to read. */
const MIN_ARROW_PX = 60;
/** The arrow lands just above a note's first letters (text is centred on its y). */
const NOTE_ARROW_INSET_PX = 12;
const NOTE_ARROW_CLEAR_PX = 18;

interface SceneArrowPath {
  id: string;
  color: string;
  d: string;
  pulse: boolean;
}

function tokenElement(tokenId: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-qtoken="${CSS.escape(tokenId)}"]`);
}

function sourceBounds(tokenIds: string[]): DOMRect | null {
  const boxes = tokenIds.map(tokenElement).filter((element): element is HTMLElement => element !== null)
    .map((element) => element.getBoundingClientRect());
  if (boxes.length !== tokenIds.length || boxes.length === 0) return null;
  const left = Math.min(...boxes.map((box) => box.left));
  const top = Math.min(...boxes.map((box) => box.top));
  const right = Math.max(...boxes.map((box) => box.right));
  const bottom = Math.max(...boxes.map((box) => box.bottom));
  return new DOMRect(left, top, right - left, bottom - top);
}

function sceneArrowPath(
  connector: SceneTeachingConnector,
  stage: HTMLElement,
  notes: TutorElement[],
  started: Set<string>,
): SceneArrowPath | null {
  const source = sourceBounds(connector.fromTokenIds);
  if (source === null) return null;
  // Points at the note itself, wherever it was placed, and only once the hand
  // has started writing it: before that the arrow points at blank canvas.
  const note = notes.find((el) => el.id === connector.toNoteId);
  if (note?.x === undefined || note.y === undefined || !started.has(note.id)) return null;
  const stageBox = stage.getBoundingClientRect();
  if (stageBox.width === 0 || stageBox.height === 0) return null;
  const startX = source.left + source.width / 2;
  // From just under the question text, below the token (which carries its own
  // mark in the same colour). From the token itself, a token on the first
  // line struck the arrow through every line under it.
  const strip = document.querySelector<HTMLElement>('[data-question-text]')?.getBoundingClientRect();
  const startY = Math.max(source.bottom, strip?.bottom ?? 0) + 4;
  const endX = stageBox.left + note.x * stageBox.width + NOTE_ARROW_INSET_PX;
  const endY = stageBox.top + note.y * stageBox.height - NOTE_ARROW_CLEAR_PX;
  const controlY = Math.max(startY + 28, (startY + endY) / 2);
  return {
    id: connector.id,
    color: TEACHING_COLORS[connector.color],
    d: `M ${startX} ${startY} Q ${(startX + endX) / 2} ${controlY} ${endX} ${endY}`,
    pulse: connector.pulse,
  };
}

export default function TeachingConnectors() {
  const connectors = useNumeraStore((state) => state.teachingConnectors);
  const tutorElements = useNumeraStore((state) => state.tutorElements);
  // Which target notes the hand has started; a string so that per-frame
  // progress updates do not re-run the layout below.
  const startedNotes = useTutorReveal((state) => connectors
    .flatMap((c) => (c.kind === 'scene' && state.progress[c.toNoteId] > 0 ? [c.toNoteId] : []))
    .join('|'));
  const [scenePaths, setScenePaths] = useState<SceneArrowPath[]>([]);

  useEffect(() => {
    const sketches = connectors.flatMap((connector) => {
      if (connector.kind !== 'token') return [];
      const from = tokenElement(connector.fromTokenId);
      const to = tokenElement(connector.toTokenId);
      if (!from || !to || from === to) return [];
      const a = from.getBoundingClientRect();
      const b = to.getBoundingClientRect();
      if (Math.hypot(a.x - b.x, a.y - b.y) < MIN_ARROW_PX) return [];
      const sketch = drawablyArrow(from, to, {
        boil: 0,
        width: 2,
        stroke: TEACHING_COLORS[connector.color],
      });
      const svg = document.body.lastElementChild;
      if (svg instanceof SVGElement && svg.classList.contains('drawably-arrow')) {
        svg.style.zIndex = '30';
        svg.style.pointerEvents = 'none';
      }
      return [sketch];
    });
    return () => sketches.forEach((sketch) => sketch.destroy());
  }, [connectors]);

  useLayoutEffect(() => {
    const sceneConnectors = connectors.filter(
      (connector): connector is SceneTeachingConnector => connector.kind === 'scene',
    );
    const stage = document.querySelector<HTMLElement>('[data-canvas-stage]');
    const started = new Set(startedNotes.split('|'));
    const updatePaths = () => {
      if (!stage) {
        setScenePaths([]);
        return;
      }
      setScenePaths(sceneConnectors.flatMap((connector) => {
        const path = sceneArrowPath(connector, stage, tutorElements, started);
        return path === null ? [] : [path];
      }));
    };
    updatePaths();
    if (!stage || sceneConnectors.length === 0) return undefined;
    const observer = new ResizeObserver(updatePaths);
    observer.observe(stage);
    sceneConnectors.forEach((connector) => connector.fromTokenIds.forEach((tokenId) => {
      const element = tokenElement(tokenId);
      if (element) observer.observe(element);
    }));
    window.addEventListener('resize', updatePaths);
    window.addEventListener('scroll', updatePaths, true);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', updatePaths);
      window.removeEventListener('scroll', updatePaths, true);
    };
  }, [connectors, tutorElements, startedNotes]);

  if (scenePaths.length === 0) return null;
  return (
    <svg className="pointer-events-none fixed inset-0 z-30 overflow-visible" aria-hidden="true">
      <defs>
        <marker id="canvas-teaching-arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M 0 0 L 8 4 L 0 8 z" fill="currentColor" />
        </marker>
      </defs>
      {scenePaths.map((path) => (
        <path
          key={path.id}
          d={path.d}
          fill="none"
          stroke={path.color}
          strokeWidth="2"
          strokeLinecap="round"
          markerEnd="url(#canvas-teaching-arrowhead)"
          style={{ color: path.color, strokeDasharray: path.pulse ? '5 4' : undefined }}
        />
      ))}
    </svg>
  );
}
