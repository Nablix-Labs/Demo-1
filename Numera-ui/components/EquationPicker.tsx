'use client';

/**
 * EquationPicker — a Demo Director control to switch the equation the tutor
 * session runs on, so the backend can be tested against different questions.
 * Picking a preset (or entering a custom concept_id / question_id) restarts the
 * session; the equation the student sees is whatever the backend returns.
 */

import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { DEMO_EQUATIONS } from '@/lib/demoEquations';

export default function EquationPicker() {
  const activeConceptId = useNumeraStore((s) => s.activeConceptId);
  const activeQuestionId = useNumeraStore((s) => s.activeQuestionId);
  const setActiveEquation = useNumeraStore((s) => s.setActiveEquation);

  const [open, setOpen] = useState(false);
  const [concept, setConcept] = useState('');
  const [question, setQuestion] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [open]);

  const active = DEMO_EQUATIONS.find((e) => e.conceptId === activeConceptId && e.questionId === activeQuestionId);
  const triggerLabel = active ? active.label : 'Custom';

  const pick = (conceptId: string, questionId: string, label?: string) => {
    setActiveEquation(conceptId, questionId, label);
    setOpen(false);
  };

  const loadCustom = () => {
    const c = concept.trim(), q = question.trim();
    if (!c || !q) return;
    pick(c, q, `${c} / ${q}`);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded border border-muted-gray bg-white px-2 py-0.5 text-[12px] font-semibold text-ink hover:border-slate-blue transition-colors"
      >
        <span className="text-slate-blue font-normal">Equation:</span>
        {triggerLabel}
        <ChevronDown size={13} strokeWidth={2} className="text-slate-blue" />
      </button>

      {open && (
        <div
          className="absolute bottom-[calc(100%+8px)] right-0 z-50 w-64 rounded-lg border border-muted-gray bg-white overflow-hidden"
          style={{ boxShadow: '0 6px 20px rgba(0,0,0,0.16)' }}
          role="menu"
        >
          <div className="px-3 py-2 border-b border-muted-gray text-[10px] font-semibold tracking-widest uppercase text-slate-blue">
            Test equation
          </div>

          <div className="py-1">
            {DEMO_EQUATIONS.map((e) => {
              const isActive = e === active;
              return (
                <button
                  key={e.id}
                  onClick={() => pick(e.conceptId, e.questionId, e.label)}
                  className={
                    'w-full flex items-center justify-between gap-2 px-3 py-1.5 text-left transition-colors ' +
                    (isActive ? 'bg-reading-surface' : 'hover:bg-reading-surface')
                  }
                >
                  <span className="text-[13px] font-semibold text-ink">{e.label}</span>
                  <span className="text-[9.5px] text-slate-blue/70 tabular-nums">{e.questionId}</span>
                </button>
              );
            })}
          </div>

          <div className="border-t border-muted-gray p-3 space-y-2">
            <div className="text-[10px] font-semibold tracking-wide uppercase text-slate-blue">Custom</div>
            <input
              value={concept}
              onChange={(ev) => setConcept(ev.target.value)}
              placeholder="concept_id"
              className="w-full rounded border border-muted-gray px-2 py-1 text-[11.5px] text-ink placeholder:text-slate-blue/60 focus:outline-none focus:border-ai-cyan"
            />
            <input
              value={question}
              onChange={(ev) => setQuestion(ev.target.value)}
              placeholder="question_id"
              onKeyDown={(ev) => ev.key === 'Enter' && loadCustom()}
              className="w-full rounded border border-muted-gray px-2 py-1 text-[11.5px] text-ink placeholder:text-slate-blue/60 focus:outline-none focus:border-ai-cyan"
            />
            <button
              onClick={loadCustom}
              disabled={!concept.trim() || !question.trim()}
              className="w-full rounded bg-focus-navy text-white py-1.5 text-[11.5px] font-semibold hover:opacity-90 disabled:opacity-30 transition-opacity"
            >
              Load &amp; restart session
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
