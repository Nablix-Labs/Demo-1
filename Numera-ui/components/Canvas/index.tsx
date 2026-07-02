'use client';

/**
 * Canvas stage — the main student workspace.
 *
 * Layout (matches wireframe):
 *   • Question pinned top-left
 *   • Bar model visual centred (backend-controlled in production)
 *   • react-konva drawing surface fills the canvas area
 *   • Floating pill toolbar at bottom-centre
 *   • Pen FAB bottom-left, Help FAB bottom-right
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useDemoTutor } from '@/hooks/useDemoTutor';
import { gridBackground, GRID_OPTIONS } from '@/lib/canvasGrid';
import Toolbar from './Toolbar';
import TeachBack from './TeachBack';

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
  const { questionText, questionNumber, items, setActiveTool, setCanvasExporter, canvasGrid, setCanvasGrid } = useNumeraStore();
  const tutor = useDemoTutor();

  const exportRef = useRef<(() => string | null) | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [gridOpen, setGridOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleExportReady = useCallback((fn: () => string | null) => {
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
    const png = exportRef.current?.();
    if (!png || items.length === 0) {
      showToast('Show your working on the canvas first, then tap Check.');
      return;
    }
    // Submit for live OCR + tutor feedback when a backend session is active;
    // otherwise acknowledge locally (mock demo).
    if (tutor.apiEnabled && tutor.sessionId) {
      showToast('Reading your working…');
      void tutor.submitCanvasWork().then((res) => {
        showToast(res ? res.tutor.tutor_message : 'Submitted — see your session trail.');
      });
    } else {
      showToast('Nice work — your working has been submitted.');
    }
  }, [items.length, showToast, tutor]);

  return (
    <main
      className="flex-1 relative min-w-0 bg-white overflow-hidden"
      aria-label="Canvas workspace"
      style={gridBackground(canvasGrid)}
    >
      {/* Question header */}
      <div className="absolute top-[26px] left-[34px] right-[34px] flex items-center gap-3 z-10">
        <div className="w-[30px] h-[30px] rounded-md border border-muted-gray bg-reading-surface flex items-center justify-center text-xs font-semibold text-slate-blue flex-shrink-0">
          {questionNumber}
        </div>
        <div className="text-[22px] font-semibold text-ink">
          Solve for{' '}
          <span className="italic font-[Cambria_Math,Georgia,serif]">x</span>:{' '}
          <span className="font-[Cambria_Math,Georgia,serif]">{questionText}</span>
        </div>
      </div>

      {/* Drawing canvas (fills entire stage, above visuals) */}
      <div className="absolute inset-0 z-[1]">
        <DrawingCanvas onExportReady={handleExportReady} />
      </div>

      {/* Teaching-back prompt */}
      <TeachBack />

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

      {/* Corner FABs */}
      <button
        onClick={() => setActiveTool('pen')}
        title="Pen"
        aria-label="Switch to pen"
        className="absolute bottom-[22px] left-6 w-12 h-12 rounded-full bg-focus-navy text-white flex items-center justify-center z-20"
        style={{ boxShadow: '0 2px 10px rgba(0,0,0,0.22)' }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 19 l1 -4 l9 -9 l3 3 l-9 9 l-4 1 z"/><line x1="13.5" y1="6.5" x2="16.5" y2="9.5"/>
        </svg>
      </button>

      {/* Paper-style + Help FABs */}
      <div className="absolute bottom-6 right-6 z-20 flex items-center gap-2.5">
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

/** Corner FAB styling — dark when open, muted when closed. */
function cnFab(open: boolean) {
  return [
    'w-10 h-10 rounded-full flex items-center justify-center transition-colors border',
    open
      ? 'bg-focus-navy text-white border-focus-navy'
      : 'bg-reading-surface text-slate-blue border-muted-gray hover:bg-muted-gray hover:text-ink',
  ].join(' ');
}
