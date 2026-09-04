'use client';

/**
 * ChatInput — lets the student type a message into the tutor chat.
 *
 * Adds the typed message to the transcript immediately, then routes it through
 * the tutor pipeline (/interaction) via useDemoTutor when a backend session is
 * active. With no backend it simply echoes into the transcript so the chat is
 * still usable in the mock demo.
 */
import { useState, type FormEvent } from 'react';
import { Send } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { rescueBlocksSubmission, RESCUE_INPUT_NOTICE } from '@/lib/rescueMode';
import { useDemoTutor } from '@/hooks/useDemoTutor';

export default function ChatInput() {
  const [text, setText] = useState('');
  const addTranscriptMessage = useNumeraStore((s) => s.addTranscriptMessage);
  const activeConceptId = useNumeraStore((s) => s.activeConceptId);
  const currentPhase = useNumeraStore((s) => s.currentPhase);
  /**
   * A rescue is running, so an ordinary answer must not be sent.
   *
   * Not a styling choice. `/interaction` evaluates a typed answer against the
   * ORIGINAL question — the one the student was already stuck on — so a message
   * sent mid-rescue is marked against that question and re-opens the scaffold
   * the rescue was escalated past. The walkthrough the student was reading is
   * replaced by the rung above it, which is the "reopen scaffold" half of
   * Chirudeva's 4 Sep report.
   */
  const blocked = useNumeraStore(rescueBlocksSubmission);
  const tutor = useDemoTutor();

  const send = (e: FormEvent) => {
    e.preventDefault();
    // Guarded here as well as on the control. A form submits on Enter whatever
    // the button looks like, and `disabled` on the button alone would leave the
    // keyboard path wide open — which is the path a child actually uses.
    if (blocked) return;
    const value = text.trim();
    if (!value) return;
    addTranscriptMessage({ role: 'student', text: value });
    setText('');
    void tutor.answer(value, {
      concept_id: activeConceptId,
      current_phase: currentPhase,
      hint_count: 0,
    });
  };

  return (
    <form
      onSubmit={send}
      className="flex items-center gap-2 px-3.5 pb-3.5 pt-2 border-t border-muted-gray flex-shrink-0"
    >
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={blocked}
        // The notice takes the placeholder's place rather than sitting above the
        // box as a fifth thing to read: it names the control that moves the turn
        // on, and it belongs where the student is trying to type.
        placeholder={blocked ? RESCUE_INPUT_NOTICE : 'Type a message…'}
        aria-label="Message Numera"
        maxLength={500}
        className="flex-1 min-w-0 rounded-md border border-muted-gray bg-white px-2.5 py-1.5 text-[11.5px] text-ink placeholder:text-slate-blue focus:outline-none focus:border-ai-cyan disabled:bg-reading-surface disabled:cursor-not-allowed"
      />
      <button
        type="submit"
        aria-label="Send message"
        disabled={blocked || !text.trim()}
        className="flex-shrink-0 w-8 h-8 rounded-md bg-ai-cyan text-ink flex items-center justify-center transition-opacity disabled:opacity-40"
      >
        <Send size={14} strokeWidth={1.8} />
      </button>
    </form>
  );
}
