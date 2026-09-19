/**
 * Capturing the canvas WITHOUT the tutor's own marks.
 *
 * The snapshot goes to OCR, and OCR is what the backend evaluates. The stage
 * holds two layers — the student's ink and the tutor's marks above it — and
 * `stage.toDataURL()` renders the whole stage, so every tutor annotation was
 * being photographed along with the student's work and read back as if the
 * student had written it.
 *
 * It is not a cosmetic problem. The tutor's reference labels are literally the
 * parts of the answer, so a turn where the student wrote nothing still came
 * back as:
 *
 *     raw_ocr_text: "Start:n\nGain: +5"
 *     detected_steps: ["Start:n", "Gain: +5"]
 *
 * — the tutor's own writing, evaluated as the student's answer, on a canvas the
 * student had not touched (Sanya, 20 Aug). Whatever the engine concluded from
 * that, it concluded about itself.
 *
 * `strokes` never had this problem: it is built from `items`, which is student
 * ink alone. Only the image was contaminated.
 */

/** The Konva bits we need, named so this is testable without a real stage. */
export interface HideableNode {
  hide(): void;
  show(): void;
}

export interface CapturableStage {
  find(selector: string): HideableNode[];
  toDataURL(config: { mimeType: string; pixelRatio: number }): string;
}

/** Konva name on every layer that carries tutor-authored marks. */
export const TUTOR_LAYER_NAME = 'tutor-layer';

/**
 * A PNG of the student's work only.
 *
 * The tutor layers are restored in a `finally`: if the capture throws — a
 * tainted canvas, an out-of-memory on a large pixelRatio — leaving them hidden
 * would silently erase the tutor's marks from the student's screen, turning a
 * failed submission into a blank lesson.
 */
export function captureStudentLayers(stage: CapturableStage): string {
  const tutorLayers = stage.find(`.${TUTOR_LAYER_NAME}`);
  tutorLayers.forEach((layer) => layer.hide());
  try {
    return stage.toDataURL({ mimeType: 'image/png', pixelRatio: 2 });
  } finally {
    tutorLayers.forEach((layer) => layer.show());
  }
}

/**
 * The stage size a snapshot was taken at.
 *
 * OCR reports where the ink is as a fraction of the IMAGE it was given, and the
 * image is the stage at capture time. Student ink, though, is stored in stage
 * pixels and never moves. So a mark placed around that ink is only right in the
 * capture's own frame: scaled by today's stage size instead, it drifts off the
 * ink the moment the canvas is any other size — a window resized, DevTools
 * docked, the side panel dragged. #329: the red ring sat beside `n + 5`
 * rather than around it, off by exactly ×1.09 across and ×1.46 down.
 *
 * Carried on each snapshot and handed back with the reply to THAT request, not
 * kept as "the last capture": the exporter also runs for the PDF panel on every
 * store change, so a module-level last-capture was the live size again by the
 * time a slow reply landed.
 */
export interface CanvasFrame { width: number; height: number }

/**
 * The pixel frame a tutor mark's 0–1 geometry is relative to: its own `frame`
 * when it was placed against captured ink, otherwise the live stage.
 */
export function frameFor(
  el: { frame?: CanvasFrame },
  width: number,
  height: number,
): CanvasFrame {
  return el.frame ?? { width, height };
}
