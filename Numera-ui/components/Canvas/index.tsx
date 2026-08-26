'use client';

/**
 * Canvas stage — the main student workspace.
 *
 * Layout (matches wireframe):
 *   • Question pinned top-left
 *   • react-konva drawing surface fills the canvas area
 *   • Floating pill toolbar at bottom-centre
 *   • Pen FAB bottom-left, Help FAB bottom-right
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useShallow } from 'zustand/react/shallow';
import { useNumeraStore, type CanvasExporter } from '@/store/useNumeraStore';
import { isPhase3 } from '@/lib/phase3';
import { useAuthStore, isConsentActive } from '@/store/useAuthStore';
import type { SchemaQuestionOption } from '@/lib/api';
import { useDemoTutor } from '@/hooks/useDemoTutor';
import { gridBackground, GRID_OPTIONS } from '@/lib/canvasGrid';
import { tutorSay } from '@/lib/tutorSpeech';
import QuestionDisplay from '@/components/QuestionDisplay';
import ScaffoldPanel from '@/components/ScaffoldPanel';
import Toolbar from './Toolbar';
import TeachBack from './TeachBack';
import { displayedQuestionNumber } from '@/lib/questionNumber';

// react-konva requires client-only rendering (no SSR)
const DrawingCanvas = dynamic(() => import('./DrawingCanvas'), { ssr: false });

const HELP_TIPS = [
  ['Pen', 'Write your working freehand.'],
  ['Eraser', 'Rub out a mistake.'],
  ['Shape', 'Drag to draw a rectangle.'],
  ['Ruler', 'Drag for a straight line.'],
  ['Colour', 'Tap the dot to change colour & thickness.'],
  ['Check', 'Submit your working when you are done.'],
];

export default function CanvasStage() {
  // Selected, not destructured off the whole store: a bare useNumeraStore()
  // subscribes to every write, and the transcript writes several times a
  // second while the student speaks — which re-rendered the entire canvas per
  // partial transcript (audit F-14).
  const { questionText, questionNumber, items, setCanvasExporter, canvasGrid, setCanvasGrid } = useNumeraStore(
    useShallow((s) => ({
      questionText: s.questionText, questionNumber: s.questionNumber, items: s.items,
      setCanvasExporter: s.setCanvasExporter, canvasGrid: s.canvasGrid, setCanvasGrid: s.setCanvasGrid,
    })),
  );
  const questionAnchors = useNumeraStore((s) => s.questionAnchors);
  const tutorOptionActionIds = useNumeraStore((s) => s.tutorOptionActionIds);
  const activeQuestionId = useNumeraStore((s) => s.activeQuestionId);
  const backendSession = useNumeraStore((s) => s.backendSession);
  // The badge counts the question's position in the served set rather than the
  // backend's running `question_number`, which is one high on the first question
  // of a phase — see lib/questionNumber.
  const shownQuestionNumber = displayedQuestionNumber(
    backendSession, activeQuestionId, questionNumber,
  );

  const activeScaffold = useNumeraStore((s) => s.activeScaffold);
  // Phase 3 spec §3.2: no scaffold panels during an independent attempt. Read
  // from the phase rather than the route — the phase is what decides whether
  // the tutor is allowed to be helping right now.
  const silentPhase3 = isPhase3(useNumeraStore((s) => s.currentPhase));
  const visualCueType = useNumeraStore((s) => s.visualCueType);
  const visualCueDescription = useNumeraStore((s) => s.visualCueDescription);
  const setVisualCueVisible = useNumeraStore((s) => s.setVisualCueVisible);
  const canvasConsents = useAuthStore((s) => s.consents);
  const canvasAllowed = isConsentActive(canvasConsents, 'canvas_processing');
  const tutor = useDemoTutor();

  // Explain Again replays the current explanation. It was gated on a visual cue
  // having arrived, which made it invisible on an ordinary question — the
  // student only ever saw it after climbing the ladder as far as VISUAL_CUE,
  // which is not what §2 asks for and is how it went missing in testing
  // (Sanya, 5 Aug). The backend implements EXPLAIN_AGAIN now, so the control
  // only needs something to replay: a tutor turn on the current question. A
  // held cue still qualifies on its own, for the offline/demo path.
  const hasTutorTurn = useNumeraStore((s) => s.transcript.some((m) => m.role === 'ai'));
  const canReplayCue = Boolean(visualCueType ?? visualCueDescription) || hasTutorTurn;

  // Choice questions. The pick is recorded and the option text goes into the
  // answer box, because the interaction contract carries no option id — an
  // answer travels as `text_input` either way. That also keeps one submit path
  // rather than a second one that only choice questions use.
  //
  // The text is REPLACED, not appended: re-picking after changing your mind
  // should swap the answer, not leave both options sitting in the box. Anything
  // the student typed after the option is preserved.
  const questionType = useNumeraStore((s) => s.questionType);
  const questionOptions = useNumeraStore((s) => s.questionOptions);
  const selectedOptionId = useNumeraStore((s) => s.selectedOptionId);
  const setSelectedOption = useNumeraStore((s) => s.setSelectedOption);
  const setTextInput = useNumeraStore((s) => s.setTextInput);
  const { explainAgain, explainAgainPending, selectOption, submitTeachBack } = tutor;
  const pickOption = useCallback(
    (option: SchemaQuestionOption) => {
      const s = useNumeraStore.getState();
      const previous = s.questionOptions.find((o) => o.option_id === s.selectedOptionId);
      const trailing = previous
        ? s.textInput.replace(previous.text, '').trimStart()
        : s.textInput.trimStart();
      setSelectedOption(option.option_id);
      setTextInput(trailing ? `${option.text} ${trailing}` : option.text);
      void selectOption(option.option_id, option.text);
    },
    [setSelectedOption, setTextInput, selectOption],
  );
  const replayCue = useCallback(() => {
    if (!explainAgainPending) void explainAgain();
  }, [explainAgain, explainAgainPending]);

  const exportRef = useRef<CanvasExporter | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [gridOpen, setGridOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleExportReady = useCallback((fn: CanvasExporter) => {
    exportRef.current = fn;
    setCanvasExporter(fn); // expose to the panel menu for "Save as PDF"
  }, [setCanvasExporter]);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2600);
  }, []);

  useEffect(() => () => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
  }, []);

  const handleCheckWork = useCallback(() => {
    if (!canvasAllowed) {
      showToast('Canvas processing is not available until the required consent is completed.');
      return;
    }
    const canvasSnapshot = exportRef.current?.();
    if (!canvasSnapshot || items.length === 0) {
      showToast('Show your working on the canvas first, then tap Check.');
      return;
    }
    // Submit for live OCR + tutor feedback when a backend session is active;
    // otherwise acknowledge locally (mock demo).
    if (tutor.apiEnabled && tutor.sessionId) {
      showToast('Reading your working…');
      void tutor.submitCanvasWork().then((res) => {
        // An accepted Phase 3 submission carries no tutor block at all — the
        // phase is silent by design — so there is nothing to quote back here.
        showToast(res?.tutor?.tutor_message?.trim() || 'Submitted — see your session trail.');
      });
    } else {
      showToast('Nice work — your working has been submitted.');
    }
  }, [canvasAllowed, items.length, showToast, tutor]);

  return (
    <main
      className="flex-1 relative min-w-0 bg-white overflow-hidden"
      aria-label="Canvas workspace"
      style={gridBackground(canvasGrid)}
    >
      {/* Question strip (§2) — question number, the task, and Explain Again.
          A bare equation gets the "Solve for x:" lead-in and maths type; anything
          with its own wording (e.g. a word problem) is shown verbatim as prose
          that wraps. See lib/questionText.ts. */}
      {/* The right padding is what keeps this clear of TeachBack, which pins
          "Explain it back" to the same corner (right-[34px]) at a higher
          z-index. Without it "Explain again" renders underneath and is simply
          invisible — which is exactly how it went missing in testing (Sanya,
          5 Aug). It also stops a long question running under that button.

          150px because that button measures 131px with the app's own styles;
          the rest is the gap. If its label changes, re-measure. */}
      <div className="absolute top-[26px] left-[34px] right-[34px] z-10">
      <div className="flex items-start gap-3 pr-[150px]">
        {shownQuestionNumber !== null && (
          <div className="w-[30px] h-[30px] rounded-md border border-muted-gray bg-reading-surface flex items-center justify-center text-xs font-semibold text-slate-blue flex-shrink-0">
            {shownQuestionNumber}
          </div>
        )}
        <QuestionDisplay
          question={questionText}
          anchors={questionAnchors}
          questionId={activeQuestionId}
          highlightedOptionIds={tutorOptionActionIds}
          size="lesson"
          questionType={questionType}
          options={questionOptions}
          selectedOptionId={selectedOptionId}
          onSelectOption={pickOption}
        />
        {/* §2: "Explain Again — replays the current concept visually without
            counting as an attempt." The backend generates the re-expression;
            while that request is in flight the disabled busy state prevents a
            second click from creating a duplicate turn. */}
        {/* §3.2: Explain Again is unavailable in Phase 3 — it is help, and the
            attempt is meant to be unaided. */}
        {!silentPhase3 && canReplayCue && (
          <button
            onClick={replayCue}
            disabled={explainAgainPending}
            aria-busy={explainAgainPending}
            className="ml-auto flex-shrink-0 rounded-full border border-muted-gray bg-white px-3.5 py-1.5 text-[12px] font-semibold text-slate-blue hover:text-ink hover:bg-reading-surface disabled:cursor-wait disabled:opacity-60 transition-colors"
          >
            {explainAgainPending ? 'Explaining…' : 'Explain again'}
          </button>
        )}
      </div>

      {/* The authorised scaffold step, on the canvas rather than in the tutor
          column. It was in the 234px chat panel, where a guiding question wrapped
          over four lines and read as another chat bubble (Manjusha, 2026-07-29).
          Here it sits under the question it is helping with, on the surface the
          student is actually working on.

          In FLOW beneath the question, not at a fixed offset. It used to be
          pinned at top-[76px], which is 50px below the question strip — exactly
          one line of it. A question that wrapped to two lines, or carried
          multiple-choice options, was covered by the card that was supposed to
          be helping with it (Manjusha, 10 Aug). */}
      {!silentPhase3 && activeScaffold && (
        <div className="mt-3 w-[min(560px,100%)]">
          <ScaffoldPanel scaffold={activeScaffold} />
        </div>
      )}
      </div>

      {/* §14: canvas consent missing */}
      {!canvasAllowed && (
        <div className="absolute top-[70px] left-[34px] right-[34px] z-10 rounded-md bg-action-orange/10 border border-action-orange/30 px-3.5 py-2 text-[12px] text-ink">
          Canvas processing is not available until the required consent is completed.
        </div>
      )}

      {/* Drawing canvas (fills entire stage) */}
      <div className="absolute inset-0 z-[1]">
        <DrawingCanvas onExportReady={handleExportReady} />
      </div>

      {/* Teaching-back prompt */}
      <TeachBack onSubmit={submitTeachBack} />

      {/* Check-work feedback toast */}
      {toast && (
        <div
          className="absolute bottom-[88px] left-1/2 -translate-x-1/2 z-30 bg-focus-navy text-white text-xs px-4 py-2.5 rounded-full flex items-center gap-2"
          style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.2)' }}
          role="status"
          aria-live="polite"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9"/><path d="M8 12 l3 3 l5 -6"/>
          </svg>
          {toast}
        </div>
      )}

      {/* Paper-style + Help FABs.

          bottom-[86px], not bottom-6. The Nablix Assist launcher is `fixed
          bottom-6 right-4 z-[60]` in the app shell, so it lands in this exact
          corner and outranks these on z — measured live on 26 Aug 2026 at a
          1440x900 viewport: the pill covers 24-74px up from the bottom edge,
          both FABs sat at 24-64px, and elementFromPoint on either one returned
          the pill. They were fully visible and completely unclickable, so
          nothing about the screen said the paper style or the canvas help was
          out of reach. 86px clears the pill's 74 with a 12px gap.

          The practice action row already dodges the same pill sideways
          (app/practice/page.tsx, right-[180px]); this cluster was missed. Up
          rather than across, because the right edge is where the FABs belong
          and the drawing toolbar owns bottom-centre. */}
      <div className="absolute bottom-[86px] right-6 z-20 flex items-center gap-2.5">
        {/* Paper / grid style picker */}
        <div className="relative">
          {gridOpen && (
            <div
              className="absolute bottom-[calc(100%+10px)] right-0 w-[236px] bg-white border border-muted-gray rounded-xl p-3"
              style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.14)' }}
              role="dialog"
              aria-label="Canvas paper style"
            >
              <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue mb-2.5">
                Paper style
              </div>
              <div className="grid grid-cols-3 gap-2">
                {GRID_OPTIONS.map((opt) => {
                  const active = canvasGrid === opt.id;
                  return (
                    <button
                      key={opt.id}
                      onClick={() => { setCanvasGrid(opt.id); setGridOpen(false); }}
                      aria-pressed={active}
                      title={opt.label}
                      className="flex flex-col items-center gap-1 group"
                    >
                      <span
                        className={
                          'w-full h-11 rounded-md bg-white transition-colors ' +
                          (active
                            ? 'ring-2 ring-focus-navy border border-focus-navy'
                            : 'border border-muted-gray group-hover:border-slate-blue')
                        }
                        style={gridBackground(opt.id)}
                      />
                      <span className={'text-[10px] font-medium ' + (active ? 'text-ink' : 'text-slate-blue')}>
                        {opt.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          <button
            onClick={() => { setGridOpen((o) => !o); setHelpOpen(false); }}
            title="Paper style"
            aria-label="Canvas paper style"
            aria-expanded={gridOpen}
            className={cnFab(gridOpen)}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16M4 15h16M10 4v16M15 4v16"/>
            </svg>
          </button>
        </div>

        {/* Help FAB + popover */}
        <div className="relative">
        {helpOpen && (
          <div
            className="absolute bottom-[calc(100%+10px)] right-0 w-64 bg-white border border-muted-gray rounded-xl p-3.5"
            style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.14)' }}
            role="dialog"
            aria-label="Canvas help"
          >
            <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue mb-2">
              Using the canvas
            </div>
            <ul className="flex flex-col gap-1.5">
              {HELP_TIPS.map(([name, desc]) => (
                <li key={name} className="text-[11.5px] leading-snug text-ink">
                  <span className="font-semibold">{name}</span>
                  <span className="text-slate-blue"> — {desc}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <button
          onClick={() => { setHelpOpen((o) => !o); setGridOpen(false); }}
          title="Help"
          aria-label="Help"
          aria-expanded={helpOpen}
          className={cnFab(helpOpen)}
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9"/><path d="M9.4 9.3 a2.6 2.6 0 1 1 3.3 2.5 c-0.8 0.3 -0.8 1 -0.8 1.7"/><circle cx="12" cy="16.6" r="0.7" fill="currentColor" stroke="none"/>
          </svg>
        </button>
        </div>
      </div>

      {/* Floating toolbar — self-positioning & draggable within the canvas */}
      <Toolbar onCheckWork={handleCheckWork} />
    </main>
  );
}

/** Corner FAB styling — dark glass when open, light glass when closed. */
function cnFab(open: boolean) {
  return [
    'w-10 h-10 rounded-full flex items-center justify-center transition-colors',
    open ? 'lg-glass-dark text-white' : 'lg-glass text-slate-blue hover:text-ink',
  ].join(' ');
}
