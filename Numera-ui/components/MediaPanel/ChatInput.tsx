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
import { useDemoTutor } from '@/hooks/useDemoTutor';
import { DEMO_PHASE } from '@/lib/api';

export default function ChatInput() {
  const [text, setText] = useState('');
  const addTranscriptMessage = useNumeraStore((s) => s.addTranscriptMessage);
  const activeConceptId = useNumeraStore((s) => s.activeConceptId);
  const activeQuestionId = useNumeraStore((s) => s.activeQuestionId);
  const tutor = useDemoTutor();

  const send = (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    addTranscriptMessage({ role: 'student', text: value });
    setText('');
    void tutor.answer(value, {
      concept_id: activeConceptId,
      question_id: activeQuestionId,
      current_phase: DEMO_PHASE,
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
        placeholder="Type a message…"
        aria-label="Message Numera"
        maxLength={500}
        className="flex-1 min-w-0 rounded-md border border-muted-gray bg-white px-2.5 py-1.5 text-[11.5px] text-ink placeholder:text-slate-blue focus:outline-none focus:border-ai-cyan"
      />
      <button
        type="submit"
        aria-label="Send message"
        disabled={!text.trim()}
        className="flex-shrink-0 w-8 h-8 rounded-md bg-ai-cyan text-ink flex items-center justify-center transition-opacity disabled:opacity-40"
      >
        <Send size={14} strokeWidth={1.8} />
      </button>
    </form>
  );
}
