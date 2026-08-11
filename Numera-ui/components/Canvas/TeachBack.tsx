'use client';

/**
 * TeachBack — a "teaching back" moment inside guided learning. The tutor asks
 * the student to explain a step in their own words; articulating it is how the
 * understanding sticks.
 *
 * The explanation is SENT. This panel used to be entirely local: "Share with
 * tutor" set a boolean and printed "Nice — explaining it back shows you really
 * understand it" no matter what the student wrote, and the words never left the
 * browser (row 33, 11 Aug). A student could type nonsense and be congratulated
 * for it, which is worse than having no feature — the whole point of teaching
 * back is that someone checks the explanation.
 *
 * It goes through the same /interaction path as any other typed answer, so it
 * lands in the transcript, the lesson trail and the tutor's turn history rather
 * than in a side channel of its own.
 */

import { useState } from 'react';
import { GraduationCap, X } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useDemoTutor } from '@/hooks/useDemoTutor';

export default function TeachBack() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [reply, setReply] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tutor = useDemoTutor();

  const close = () => {
    setOpen(false);
    setReply(null);
    setError(null);
    setText('');
  };

  const share = async () => {
    const explanation = text.trim();
    if (!explanation || sending) return;
    setSending(true);
    setError(null);
    const s = useNumeraStore.getState();
    const res = await tutor.answer(explanation, {
      concept_id: s.activeConceptId,
      current_phase: s.currentPhase,
      hint_count: s.lastHintText ? 1 : 0,
    });
    setSending(false);
    if (!res) {
      // Without a live session there is nobody to read it. Say so rather than
      // printing praise for an explanation that was never assessed.
      setError("That didn't reach the tutor. Your explanation is still here — try once more.");
      return;
    }
    // The tutor's own words about THIS explanation, not a canned line.
    setReply(res.message);
  };

  return (
    <div className="absolute top-[22px] right-[34px] z-20">
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className="lg-glass flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold text-ink transition-colors"
        >
          <GraduationCap size={15} strokeWidth={1.8} /> Explain it back
        </button>
      ) : (
        <div className="w-[300px] bg-white border border-muted-gray rounded-xl overflow-hidden" style={{ boxShadow: '0 6px 22px rgba(0,0,0,0.16)' }}>
          <div className="flex items-center justify-between px-4 py-3 border-b border-muted-gray">
            <span className="flex items-center gap-1.5 text-[12.5px] font-semibold text-ink">
              <GraduationCap size={15} strokeWidth={1.8} /> Teach it back
            </span>
            <button onClick={close} aria-label="Close" className="w-6 h-6 rounded-md flex items-center justify-center text-slate-blue hover:bg-reading-surface">
              <X size={15} strokeWidth={1.8} />
            </button>
          </div>
          <div className="p-4">
            {reply === null ? (
              <>
                <p className="text-[12.5px] text-slate-blue leading-snug mb-3">
                  In your own words — how would you explain the first step to a friend?
                </p>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={3}
                  placeholder="Type your explanation…"
                  disabled={sending}
                  className="w-full rounded-md border border-muted-gray px-3 py-2 text-[12.5px] outline-none focus:border-ai-cyan resize-none disabled:opacity-60"
                />
                {error && (
                  <p role="alert" className="mt-2 text-[12px] text-action-orange">{error}</p>
                )}
                <button
                  onClick={() => void share()}
                  disabled={!text.trim() || sending}
                  aria-busy={sending}
                  className={
                    'mt-3 w-full rounded-md px-4 py-2 text-[12.5px] font-semibold transition-opacity ' +
                    (text.trim() && !sending
                      ? 'bg-focus-navy text-white hover:opacity-80'
                      : 'bg-muted-gray text-slate-blue')
                  }
                >
                  {sending ? 'Sending…' : 'Share with tutor'}
                </button>
              </>
            ) : (
              <p className="text-[12.5px] text-ink leading-snug">{reply}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
