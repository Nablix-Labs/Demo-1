'use client';

/**
 * How a question appears on screen.
 *
 * One component rather than three copies of the same conditional, because the
 * screens had already drifted: the lesson canvas, independent practice and the
 * diagnostic each re-implemented "is this an equation or prose?" slightly
 * differently, and none of them handled a stack of cases at all.
 *
 * The layout decision itself is in lib/questionText.ts — this only draws it.
 */

import { questionLayout } from '@/lib/questionText';
import { fragmentRanges, type QuestionAnchor } from '@/lib/questionAnchors';
import AnchoredText from '@/components/AnchoredText';
import type { QuestionType, SchemaQuestionOption } from '@/lib/api';
import { cn } from '@/lib/cn';

// Set via `style` rather than an arbitrary Tailwind class: the class would have
// to be interpolated, and Tailwind's scanner only sees class strings written out
// literally — an interpolated one silently produces no CSS at all.
const MATHS_FONT = { fontFamily: 'Cambria Math, Georgia, serif' } as const;

/**
 * The choices for a question that has them.
 *
 * Labelled A, B, C rather than left bare: the tutor refers to options by letter
 * when it speaks, and a student answering by voice needs something to say. The
 * letter is positional and comes from the order the Student Model sent, so it
 * matches what the tutor is looking at.
 *
 * Selecting is not submitting. CHOICE_WITH_EXPLANATION wants the reasoning as
 * well as the pick, and the interaction contract has no `option_id` field — the
 * answer travels as `text_input` — so choosing writes the option into the answer
 * box and leaves the student to finish the sentence.
 */
function Options({
  options,
  selectedId,
  onSelect,
  requiresExplanation,
  readOnly = false,
}: {
  options: SchemaQuestionOption[];
  selectedId: string | null;
  onSelect: (option: SchemaQuestionOption) => void;
  requiresExplanation: boolean;
  /** Shown but not changeable — a Phase 3 answer that has been accepted. */
  readOnly?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1.5" role="radiogroup" aria-label="Answer options">
      {options.map((option, i) => {
        const selected = option.option_id === selectedId;
        return (
          <button
            key={option.option_id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={readOnly}
            onClick={() => onSelect(option)}
            className={cn(
              'group flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-[14px] transition-colors',
              selected
                ? 'border-focus-navy bg-focus-navy/5 text-ink font-medium'
                : 'border-muted-gray bg-white text-ink',
              // A locked choice still SHOWS what was picked — hiding it would
              // erase the student's own answer from the screen — but it must
              // not look pressable.
              readOnly ? 'cursor-default opacity-90' : !selected && 'hover:bg-reading-surface',
            )}
          >
            <span
              className={cn(
                'flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md border text-[11px] font-semibold',
                selected
                  ? 'border-focus-navy bg-focus-navy text-white'
                  : 'border-muted-gray bg-reading-surface text-slate-blue',
              )}
              aria-hidden="true"
            >
              {String.fromCharCode(65 + i)}
            </span>
            <span style={MATHS_FONT}>{option.text}</span>
          </button>
        );
      })}
      {requiresExplanation && (
        <p className="text-[12px] text-slate-blue mt-0.5">
          {selectedId
            ? 'Now say or write why you picked it.'
            : 'Pick one, then explain why.'}
        </p>
      )}
    </div>
  );
}


/**
 * `from`/`to` props for one fragment, resolved against the original question.
 *
 * Undefined when the fragment is not a slice of the question (an added lead-in),
 * which makes AnchoredText render it plainly — correct, since the backend never
 * measured text it did not send.
 */
function spanProps(range: { from: number | null; to: number | null }) {
  return range.from === null ? {} : { from: range.from, to: range.to as number };
}

export default function QuestionDisplay({
  question,
  size = 'lesson',
  questionType = null,
  options = [],
  selectedOptionId = null,
  onSelectOption,
  optionsReadOnly = false,
  anchors,
}: {
  question: string;
  /** `lesson` is the full canvas header; `compact` is the practice header. */
  size?: 'lesson' | 'compact';
  /** Drives whether options render. Null renders the question alone. */
  questionType?: QuestionType | null;
  options?: SchemaQuestionOption[];
  selectedOptionId?: string | null;
  onSelectOption?: (option: SchemaQuestionOption) => void;
  /** Render the choices as a record of what was picked, not a chooser. */
  optionsReadOnly?: boolean;
  /**
   * Spans of `question` the tutor is pointing at (Chirudeva handoff §1).
   *
   * The offsets index `question` as sent, but this component renders it in
   * FRAGMENTS — a bare equation gets a lead-in wrapped round it, a run of cases
   * is split into a grid — so each fragment is resolved back to its own range
   * before its anchors are drawn. `fragmentRanges` does that with one moving
   * cursor, in render order.
   */
  anchors?: QuestionAnchor[];
}) {
  const layout = questionLayout(question);
  const equationSize = size === 'lesson' ? 'text-[22px]' : 'text-[16px]';
  const proseSize = size === 'lesson' ? 'text-[17px]' : 'text-[14px]';

  // A question that expects a choice but arrived with none falls back to free
  // response. Rendering an empty chooser would leave the student looking at a
  // question with no way to answer it.
  const showOptions = Boolean(onSelectOption) && options.length > 0 && questionType !== null
    && questionType !== 'SHORT_RESPONSE' && questionType !== 'MULTI_PART_SHORT_RESPONSE';
  const requiresExplanation =
    questionType === 'CHOICE_WITH_EXPLANATION' || questionType === 'TRUE_FALSE_WITH_EXPLANATION';

  const optionList = showOptions ? (
    <Options
      options={options}
      selectedId={selectedOptionId}
      onSelect={onSelectOption!}
      requiresExplanation={requiresExplanation}
      readOnly={optionsReadOnly}
    />
  ) : null;

  if (layout.kind === 'equation') {
    return (
      <div className="flex flex-col gap-3">
        <div className={`${equationSize} font-semibold text-ink`}>
          {/* The lead-in is added text, not part of the question, so it carries
              no anchors — see fragmentRanges. */}
          Solve for <span className="italic" style={MATHS_FONT}>x</span>:{' '}
          <span style={MATHS_FONT}>
            <AnchoredText
              question={question}
              anchors={anchors}
              {...spanProps(fragmentRanges(question, [layout.text])[0])}
            />
          </span>
        </div>
        {optionList}
      </div>
    );
  }

  if (layout.kind === 'cases') {
    // §3: "The alignment itself should reveal that the left values change while
    // +5 remains fixed." Columns are right-aligned so units digits line up —
    // 14 sits under 9, not one character to its right — and tabular numerals
    // keep every digit the same width regardless of the glyphs involved.
    const columns = layout.rows[0].length;
    // Every fragment this branch renders, in the order it renders them, so one
    // cursor resolves them all — a stack of cases repeats "+ 5" verbatim, and
    // each occurrence must claim its own position.
    const cells = layout.rows.flat();
    const ranges = fragmentRanges(
      question,
      layout.instruction ? [...cells, layout.instruction] : cells,
    );
    return (
      <div className="flex flex-col gap-2">
        <div
          className={`${equationSize} font-semibold text-ink inline-grid gap-x-4 gap-y-1 tabular-nums`}
          style={{ ...MATHS_FONT, gridTemplateColumns: `repeat(${columns}, auto)` }}
          role="group"
          aria-label="Cases to compare"
        >
          {layout.rows.map((row, r) =>
            row.map((cell, c) => (
              <span key={`${r}-${c}`} className="text-right">
                <AnchoredText
                  question={question}
                  anchors={anchors}
                  {...spanProps(ranges[r * columns + c])}
                />
              </span>
            )),
          )}
        </div>
        {/* The task, kept below the evidence it refers to — the spec's question
            strip / evidence area split. */}
        {layout.instruction && (
          <p className={`${proseSize} font-medium text-ink leading-snug max-w-[62ch]`}>
            <AnchoredText
              question={question}
              anchors={anchors}
              {...spanProps(ranges[cells.length])}
            />
          </p>
        )}
        {optionList}
      </div>
    );
  }

  // Prose. `whitespace-pre-line` keeps any line breaks the backend sent — they
  // are deliberate, and collapsing them is what flattened the stacked cases in
  // the first place — while still letting long lines wrap.
  return (
    <div className="flex flex-col gap-3">
      <p
        className={`${proseSize} font-semibold text-ink leading-snug max-w-[62ch] whitespace-pre-line`}
      >
        {/* `layout.text` is the question trimmed, so its range is resolved
            rather than assumed to start at 0 — leading whitespace would shift
            every anchor by exactly the amount that was trimmed. */}
        <AnchoredText
          question={question}
          anchors={anchors}
          {...spanProps(fragmentRanges(question, [layout.text])[0])}
        />
      </p>
      {optionList}
    </div>
  );
}
