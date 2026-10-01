import sceneSlots from '@/config/canvasTeachingSceneSlots.json';
import type { CanvasBBox } from '@/lib/canvasMemory';
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
/**
 * A note tied to question tokens sits under them, but never left of the
 * reasoning column: x < 0.40 is where the student writes (handoff rule 5).
 */
const NOTE_MIN_X = 0.44;
const NOTE_MAX_X = 0.78;
/** How far a note starts left of its token's centre, so the arrow lands on its first letters. */
const NOTE_LEAD = 0.02;
const NOTE_ROW_GAP = 0.085;
const NOTE_LAST_Y = 0.86;
/** Rough footprint of a note, for keeping two of them apart. */
const NOTE_WIDTH = 0.22;
const NOTE_HEIGHT = 0.06;

export function sceneNoteId(questionId: string, slotId: string): string {
  return `ctp:scene:${questionId}:${slotId}:note`;
}

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
  source: CanvasBBox | null = null,
): TutorElement[] | null {
  const id = `ctp:scene:${questionId}:${slotId}`;
  if (existing.some((element) => element.id === `${id}:note`)) return [];
  const placement = sceneNotePlacement(questionId, slotId, top, existing, source);
  if (placement === null) return null;
  const { slot, x, y } = placement;
  const ink = colors.NAVY;
  // A handwritten slot writes maths as ink, so the LaTeX has to become the
  // symbols a hand would write. Anything that does not reduce cleanly is set
  // with KaTeX instead: before this, a WRITE_MATH in a handwritten slot put
  // the source itself on the board — `\frac{c}{d}=c\div d` (live, 28 Sep).
  const handwritten = operationKind === 'WRITE_MATH' ? handwrittenMath(content) : content;
  const note: TutorElement = handwritten === null || (operationKind === 'WRITE_MATH' && slot.format === 'typeset')
    ? { id: `${id}:note`, kind: 'math', x, y, tex: content, color: ink, size: NOTE_SIZE }
    : {
        id: `${id}:note`, kind: 'text', x, y, text: handwritten, color: ink,
        size: NOTE_SIZE,
      };
  const box: TutorElement[] = slot.box
    ? [{
        id: `${id}:box`, kind: 'rect', x: x - 0.018, y: y - BOX_HEIGHT / 2,
        w: BOX_WIDTH, h: BOX_HEIGHT, color: ink, strokeWidth: 2,
      }]
    : [];
  // No arrow of its own: the only arrow into a note is the CONNECT from the
  // question tokens it is about (TeachingConnectors). A stub drawn here pointed
  // down from empty canvas, often through the question text (live, 1 Oct).
  return [...box, note];
}

/**
 * Simple LaTeX as the characters a hand would write, or null when it does not
 * reduce to plain symbols (the caller then typesets it).
 */
export function handwrittenMath(tex: string): string | null {
  let out = tex;
  // Innermost first, so a fraction inside a fraction still reduces.
  for (let i = 0; i < 4; i += 1) {
    out = out.replace(/\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}/g, (_m, a: string, b: string) => {
      const wrap = (v: string) => (/^[\w²³]+$/.test(v.trim()) ? v.trim() : `(${v.trim()})`);
      return `${wrap(a)}/${wrap(b)}`;
    });
  }
  out = out
    .replace(/\\left|\\right/g, '')
    .replace(/\\times/g, '×').replace(/\\div/g, '÷').replace(/\\cdot/g, '·')
    .replace(/\\neq/g, '≠').replace(/\\leq?/g, '≤').replace(/\\geq?/g, '≥').replace(/\\pm/g, '±')
    .replace(/\^\{?2\}?/g, '²').replace(/\^\{?3\}?/g, '³')
    .replace(/\\[,;:! ]/g, ' ')
    .replace(/\s*([=×÷+−·≠≤≥])\s*/g, ' $1 ')
    .replace(/\s+/g, ' ')
    .trim();
  return /[\\{}^_]/.test(out) || !out ? null : out;
}

export function sceneNotePlacement(
  questionId: string,
  slotId: string,
  top: number,
  existing: TutorElement[],
  source: CanvasBBox | null = null,
): SceneNotePlacement | null {
  const slot = sceneSlot(slotId);
  if (slot === null) return null;
  const id = `ctp:scene:${questionId}:${slotId}`;
  if (existing.some((element) => element.id === `${id}:note`)) return null;
  if (source !== null) {
    // Under the tokens the note is about, so the arrow from them is short and
    // reads as "this, here". The slot's fixed column ignored the tokens and
    // put the note wherever the slot table said.
    // Taken spots push the note RIGHT along the row before they push it down:
    // a note stepped down under an earlier one had its arrow struck through
    // that note (live, Q-T01-006, 1 Oct).
    const x0 = Math.min(NOTE_MAX_X, Math.max(NOTE_MIN_X, source.x + source.w / 2 - NOTE_LEAD));
    for (let y = Math.max(top, source.y + source.h + NOTE_ROW_GAP); y < NOTE_LAST_Y; y += NOTE_ROW_GAP) {
      for (let x = x0; x <= NOTE_MAX_X; x += NOTE_WIDTH) {
        if (!taken(existing, x, y)) return { x, y, slot };
      }
    }
    return { x: x0, y: NOTE_LAST_Y, slot };
  }
  const genericRows = slotId.startsWith('generic_confirmation:')
    ? existing.filter((element) => element.id.startsWith(`ctp:scene:${questionId}:generic_confirmation:`) && element.id.endsWith(':note')).length
    : 0;
  let y = top + (slot.row + genericRows) * SCENE_ROW_GAP;
  // A note placed under its tokens may already sit in this slot.
  while (y < NOTE_LAST_Y && taken(existing, slot.x, y)) y += SCENE_ROW_GAP;
  return { x: slot.x, y, slot };
}

/** Is there already a mark within a note's footprint of (x, y)? */
function taken(existing: TutorElement[], x: number, y: number): boolean {
  return existing.some((el) => el.x !== undefined && el.y !== undefined
    && Math.abs(el.y - y) < NOTE_HEIGHT && Math.abs(el.x - x) < NOTE_WIDTH);
}
