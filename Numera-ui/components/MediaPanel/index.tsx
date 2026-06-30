'use client';

import { useEffect, useRef, useState } from 'react';
import { MoreVertical, PanelLeft, PanelRight, Eye, EyeOff, FileDown } from 'lucide-react';
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
  const { panelSide, transcriptVisible, togglePanelSide, toggleTranscript } = useNumeraStore();
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

  const item = 'w-full flex items-center gap-2.5 px-3 py-2 text-[12px] text-[#1a1a1a] hover:bg-[#f4f4f4] transition-colors text-left';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Panel options"
        aria-expanded={open}
        className="w-6 h-6 -mr-1 rounded-md flex items-center justify-center text-[#7a7a7a] hover:bg-[#f4f4f4] hover:text-[#1a1a1a] transition-colors"
      >
        <MoreVertical size={16} strokeWidth={1.8} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-[calc(100%+6px)] z-30 w-44 bg-white border border-[#9a9a9a] rounded-lg overflow-hidden py-1"
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
          <div className="h-[1px] bg-[#eaeaea] my-1" />
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

  return (
    <aside
      // pb clears the fixed Demo Director bar (FlowControls) so the chat input
      // at the bottom isn't hidden behind it.
      className="flex flex-col flex-shrink-0 border-r border-[#c8c8c8] min-h-0 pb-12"
      style={{ width: 234 }}
      aria-label="Tutor and student panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3.5 py-3.5 border-b border-[#c8c8c8] flex-shrink-0">
        <div>
          <div className="text-sm font-semibold tracking-[0.4px]">Numera</div>
          <div className="text-[8.5px] font-normal text-[#9a9a9a] tracking-[1.5px] uppercase">by Nablix</div>
        </div>
        <div className="flex items-center gap-2">
          <div className="border border-[#9a9a9a] rounded-full px-2.5 py-1 text-[10px] tracking-[0.4px] flex items-center gap-1.5 text-[#7a7a7a]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#1a1a1a] inline-block" />
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
    </aside>
  );
}
