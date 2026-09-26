import sceneSlots from '@/config/canvasTeachingSceneSlots.json';
import type { CanvasTeachingColor, CanvasTeachingOperationKind } from '@/lib/canvasTeachingPlan';
import type { TutorElement } from '@/store/useNumeraStore';

interface SceneSlot {
  x: number;
  row: number;
  accent: CanvasTeachingColor;
  format: 'handwritten' | 'typeset';
  box: boolean;
}

const SCENE_ROW_GAP = 0.12;
const NOTE_SIZE = 24;
const BOX_WIDTH = 0.2;
const BOX_HEIGHT = 0.07;
const ARROW_GAP = 0.055;

function sceneSlot(slotId: string): SceneSlot | null {
  const slot = sceneSlots[slotId as keyof typeof sceneSlots];
  if (!slot || !isCanvasTeachingColor(slot.accent) || !isSceneFormat(slot.format)) return null;
  return { ...slot, accent: slot.accent, format: slot.format };
}

function isCanvasTeachingColor(value: string): value is CanvasTeachingColor {
  return value === 'AMBER' || value === 'TEAL' || value === 'NAVY';
}

function isSceneFormat(value: string): value is SceneSlot['format'] {
  return value === 'handwritten' || value === 'typeset';
}

export function sceneNoteElements(
  questionId: string,
  slotId: string,
  operationKind: CanvasTeachingOperationKind,
  content: string,
  top: number,
  colors: Record<CanvasTeachingColor, string>,
  existing: TutorElement[],
): TutorElement[] | null {
  const slot = sceneSlot(slotId);
  if (slot === null) return null;

  const id = `ctp:scene:${questionId}:${slotId}`;
  if (existing.some((element) => element.id === `${id}:note`)) return [];

  const y = top + slot.row * SCENE_ROW_GAP;
  const ink = colors.NAVY;
  const note: TutorElement = operationKind === 'WRITE_MATH' && slot.format === 'typeset'
    ? { id: `${id}:note`, kind: 'math', x: slot.x, y, tex: content, color: ink, size: NOTE_SIZE }
    : {
        id: `${id}:note`, kind: 'text', x: slot.x, y, text: content, color: ink,
        size: NOTE_SIZE,
      };
  const arrow: TutorElement = {
    id: `${id}:arrow`, kind: 'arrow', color: colors[slot.accent], strokeWidth: 2,
    from: [slot.x + 0.035, Math.max(0, y - ARROW_GAP)],
    to: [slot.x + 0.035, y - 0.012],
  };
  const box: TutorElement[] = slot.box
    ? [{
        id: `${id}:box`, kind: 'rect', x: slot.x - 0.018, y: y - BOX_HEIGHT / 2,
        w: BOX_WIDTH, h: BOX_HEIGHT, color: ink, strokeWidth: 2,
      }]
    : [];
  return [arrow, ...box, note];
}
