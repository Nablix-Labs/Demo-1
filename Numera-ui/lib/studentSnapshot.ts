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
