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

export interface SceneNotePlacement {
  x: number;
  y: number;
  slot: SceneSlot;
}

const SCENE_ROW_GAP = 0.12;
const NOTE_SIZE = 24;
const BOX_WIDTH = 0.2;
const BOX_HEIGHT = 0.07;
const ARROW_GAP = 0.055;

function sceneSlot(slotId: string): SceneSlot | null {
  const baseSlotId = slotId.split(':', 1)[0];
  const slot = sceneSlots[baseSlotId as keyof typeof sceneSlots];
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
  const id = `ctp:scene:${questionId}:${slotId}`;
  if (existing.some((element) => element.id === `${id}:note`)) return [];
  const placement = sceneNotePlacement(questionId, slotId, top, existing);
  if (placement === null) return null;
  const { slot, x, y } = placement;
  const ink = colors.NAVY;
  const note: TutorElement = operationKind === 'WRITE_MATH' && slot.format === 'typeset'
    ? { id: `${id}:note`, kind: 'math', x, y, tex: content, color: ink, size: NOTE_SIZE }
    : {
        id: `${id}:note`, kind: 'text', x, y, text: content, color: ink,
        size: NOTE_SIZE,
      };
  const arrow: TutorElement = {
    id: `${id}:arrow`, kind: 'arrow', color: colors[slot.accent], strokeWidth: 2,
    from: [x + 0.035, Math.max(0, y - ARROW_GAP)],
    to: [x + 0.035, y - 0.012],
  };
  const box: TutorElement[] = slot.box
    ? [{
        id: `${id}:box`, kind: 'rect', x: x - 0.018, y: y - BOX_HEIGHT / 2,
        w: BOX_WIDTH, h: BOX_HEIGHT, color: ink, strokeWidth: 2,
      }]
    : [];
  return [arrow, ...box, note];
}

export function sceneNotePlacement(
  questionId: string,
  slotId: string,
  top: number,
  existing: TutorElement[],
): SceneNotePlacement | null {
  const slot = sceneSlot(slotId);
  if (slot === null) return null;
  const id = `ctp:scene:${questionId}:${slotId}`;
  if (existing.some((element) => element.id === `${id}:note`)) return null;
  const genericRows = slotId.startsWith('generic_confirmation:')
    ? existing.filter((element) => element.id.startsWith(`ctp:scene:${questionId}:generic_confirmation:`) && element.id.endsWith(':note')).length
    : 0;
  return { x: slot.x, y: top + (slot.row + genericRows) * SCENE_ROW_GAP, slot };
}
