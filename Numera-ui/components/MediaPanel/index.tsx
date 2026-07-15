'use client';

import { useEffect, useRef, useState } from 'react';
import { MoreVertical, PanelLeft, PanelRight, Eye, EyeOff, FileDown, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { exportNotesPDF } from '@/lib/exportNotes';
import TutorTile from './TutorTile';
import VoiceBar from './VoiceBar';
import Transcript from './Transcript';
import ChatInput from './ChatInput';
import { cn } from '@/lib/cn';

const stateLabel: Record<string, string> = {
  idle:    'Idle',
  state_1: 'Warm-up',
  state_2: 'Explanation',
  state_3: 'Step-by-step',
  state_4: 'Guided Practice',
  state_5: 'Review',
};

/** ⋮ overflow menu — panel side + transcript visibility. */
function PanelMenu() {
  const { panelSide, transcriptVisible, togglePanelSide, toggleTranscript, togglePanelCollapsed } = useNumeraStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const saveNotes = async () => {
    const s = useNumeraStore.getState();
    await exportNotesPDF({
      questionNumber: s.questionNumber,
      questionText: s.questionText,
      canvasPng: s.canvasExporter?.() ?? null,
      transcript: s.transcript,
    });
  };

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const item = 'w-full flex items-center gap-2.5 px-3 py-2 text-[12px] text-ink hover:bg-reading-surface transition-colors text-left';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Panel options"
        aria-expanded={open}
        className="w-6 h-6 -mr-1 rounded-md flex items-center justify-center text-slate-blue hover:bg-reading-surface hover:text-ink transition-colors"
      >
        <MoreVertical size={16} strokeWidth={1.8} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-[calc(100%+6px)] z-30 w-44 bg-white border border-muted-gray rounded-lg overflow-hidden py-1"
          style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.14)' }}
          role="menu"
        >
          <button className={item} onClick={() => { togglePanelSide(); setOpen(false); }}>
            {panelSide === 'left'
              ? <><PanelRight size={15} strokeWidth={1.7} /> Move panel right</>
              : <><PanelLeft size={15} strokeWidth={1.7} /> Move panel left</>}
          </button>
          <button className={item} onClick={() => { toggleTranscript(); setOpen(false); }}>
            {transcriptVisible
              ? <><EyeOff size={15} strokeWidth={1.7} /> Hide transcript</>
              : <><Eye size={15} strokeWidth={1.7} /> Show transcript</>}
          </button>
          <button className={item} onClick={() => { togglePanelCollapsed(); setOpen(false); }}>
            <ChevronsLeft size={15} strokeWidth={1.7} /> Collapse panel
          </button>
          <div className="h-[1px] bg-muted-gray my-1" />
          <button className={item} onClick={() => { setOpen(false); void saveNotes(); }}>
            <FileDown size={15} strokeWidth={1.7} /> Save notes as PDF
          </button>
        </div>
      )}
    </div>
  );
}

export default function MediaPanel() {
  const sessionState = useNumeraStore((s) => s.sessionState);
  const transcriptVisible = useNumeraStore((s) => s.transcriptVisible);
  const panelSide = useNumeraStore((s) => s.panelSide);
  const panelCollapsed = useNumeraStore((s) => s.panelCollapsed);
  const togglePanelCollapsed = useNumeraStore((s) => s.togglePanelCollapsed);

  // Single root element throughout, so collapsing animates the width instead
  // of unmounting/remounting a differently-typed node (which would also drop
  // any in-flight state, e.g. an open PanelMenu).
  const ExpandIcon = panelSide === 'left' ? ChevronsRight : ChevronsLeft;

  return (
    <aside
      className={cn(
        'lg-glass flex flex-col flex-shrink-0 min-h-0 overflow-hidden rounded-2xl my-2',
        panelSide === 'left' ? 'ml-0 mr-2' : 'mr-0 ml-2',
        'transition-[width] duration-200 ease-in-out'
      )}
      style={{ width: panelCollapsed ? 28 : 234 }}
      aria-label="Tutor and student panel"
    >
      {panelCollapsed ? (
        <button
          onClick={togglePanelCollapsed}
          aria-label="Expand panel"
          title="Expand panel"
          className="mt-3.5 mx-auto w-6 h-6 rounded-md flex items-center justify-center text-slate-blue hover:bg-reading-surface hover:text-ink transition-colors flex-shrink-0"
        >
          <ExpandIcon size={15} strokeWidth={1.8} />
        </button>
      ) : (
        // Fixed inner width so content doesn't reflow/wrap while the outer
        // <aside> is mid-transition between 234px and 28px.
        <div
          className="flex flex-col min-h-0 h-full"
          style={{ width: 234 }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3.5 py-3.5 border-b border-muted-gray flex-shrink-0">
            <div>
              <div className="text-sm font-semibold tracking-[0.4px]">Numera</div>
              <div className="text-[8.5px] font-normal text-slate-blue tracking-[1.5px] uppercase">by Nablix</div>
            </div>
            <div className="flex items-center gap-2">
              <div className="border border-muted-gray rounded-full px-2.5 py-1 text-[10px] tracking-[0.4px] flex items-center gap-1.5 text-slate-blue">
                <span className="w-1.5 h-1.5 rounded-full bg-ai-cyan inline-block" />
                {stateLabel[sessionState] ?? 'Guided'}
              </div>
              <PanelMenu />
            </div>
          </div>

          {/* Tutor tile */}
          <div className="px-3.5 pt-3.5 pb-1.5 flex flex-col gap-3 flex-shrink-0">
            <TutorTile />
          </div>

          {/* Voice controls */}
          <VoiceBar />

          {/* Transcript (optional) + chat input */}
          {transcriptVisible
            ? (
              <>
                <Transcript />
                <ChatInput />
              </>
            )
            : <div className={cn('flex-1 min-h-0')} aria-hidden="true" />}
        </div>
      )}
    </aside>
  );
}
