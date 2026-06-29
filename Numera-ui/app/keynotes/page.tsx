'use client';

/**
 * Key Notes at a Glance — the revision-notes page generated after the session.
 * Topic-wise cards of the summary, tips, tricks and formulas covered, so the
 * student can revise quickly before an exam. Each card can be read out loud.
 */

import { useCallback, useState } from 'react';
import { Volume2, Square, Sparkles, Flag } from 'lucide-react';
import PageShell, { Chip } from '@/components/PageShell';
import { KEY_NOTES, noteToSpeech, type KeyNote } from '@/lib/keynotes';

function speak(text: string, onEnd: () => void) {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) { onEnd(); return; }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.98;
  u.onend = onEnd;
  u.onerror = onEnd;
  window.speechSynthesis.speak(u);
}

export default function KeyNotesPage() {
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  const stop = useCallback(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel();
    setSpeakingId(null);
  }, []);

  const toggle = useCallback((n: KeyNote) => {
    if (speakingId === n.id) { stop(); return; }
    setSpeakingId(n.id);
    speak(noteToSpeech(n), () => setSpeakingId(null));
  }, [speakingId, stop]);

  return (
    <PageShell
      title="Key Notes at a glance"
      subtitle="Quick revision from today’s session — read before your exam."
      action={<Chip tone="outline">{KEY_NOTES.length} topics</Chip>}
    >
      <div className="flex flex-col gap-5 max-w-3xl">
        {KEY_NOTES.map((n) => (
          <article key={n.id} className="rounded-xl border border-[#c8c8c8] bg-white overflow-hidden">
            {/* header */}
            <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-[#eaeaea]">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="text-[16px] font-semibold text-[#1a1a1a]">{n.topic}</h2>
                  {n.flagged && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-[#f4f4f4] px-2 py-0.5 text-[10px] font-semibold tracking-[0.4px] uppercase text-[#7a7a7a]">
                      <Flag size={10} strokeWidth={2} /> Your slip today
                    </span>
                  )}
                </div>
                <p className="text-[12.5px] text-[#5a5a5a] mt-1 leading-relaxed">{n.meaning}</p>
              </div>
              <button
                onClick={() => toggle(n)}
                aria-label={speakingId === n.id ? 'Stop reading' : 'Read out loud'}
                className="flex-shrink-0 inline-flex items-center gap-1.5 rounded-md border border-[#1a1a1a] px-3 py-1.5 text-[12px] font-semibold text-[#1a1a1a] hover:bg-[#1a1a1a] hover:text-white transition-colors"
              >
                {speakingId === n.id ? <><Square size={13} strokeWidth={2.2} /> Stop</> : <><Volume2 size={14} strokeWidth={1.9} /> Read</>}
              </button>
            </div>

            {/* body */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5 px-6 py-5">
              <Block label="How to start">
                <p className="text-[13px] text-[#3a3a3a] leading-relaxed">{n.howToStart}</p>
              </Block>

              <Block label="Formula / rule">
                <div className="rounded-md border border-[#9a9a9a] bg-[#f4f4f4] px-3 py-2 text-[14px] text-[#1a1a1a] font-[Cambria_Math,Georgia,serif]">
                  {n.formula}
                </div>
              </Block>

              <Block label="Steps to follow">
                <ol className="flex flex-col gap-1">
                  {n.steps.map((s, idx) => (
                    <li key={idx} className="flex gap-2 text-[13px] text-[#3a3a3a]">
                      <span className="text-[#9a9a9a] font-semibold tabular-nums">{idx + 1}.</span>
                      <span>{s}</span>
                    </li>
                  ))}
                </ol>
              </Block>

              <div className="flex flex-col gap-5">
                <Block label="Be careful with">
                  <ul className="flex flex-col gap-1">
                    {n.beCareful.map((b, idx) => (
                      <li key={idx} className="flex gap-2 text-[13px] text-[#3a3a3a]">
                        <span className="text-[#9a9a9a]">•</span><span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </Block>

                <Block label="Tips & tricks">
                  <ul className="flex flex-col gap-1">
                    {n.tips.map((t, idx) => (
                      <li key={idx} className="flex gap-2 text-[13px] text-[#3a3a3a]">
                        <Sparkles size={13} strokeWidth={1.8} className="mt-0.5 flex-shrink-0 text-[#7a7a7a]" />
                        <span>{t}</span>
                      </li>
                    ))}
                  </ul>
                </Block>
              </div>

              <Block label="Mini example">
                <div className="rounded-md border border-[#c8c8c8] bg-white px-3 py-2.5 flex flex-col gap-0.5">
                  {n.example.map((e, idx) => (
                    <span key={idx} className="text-[14px] text-[#1a1a1a] font-[Cambria_Math,Georgia,serif]">{e}</span>
                  ))}
                </div>
              </Block>

              <Block label="Exam reminder">
                <p className="text-[13px] text-[#3a3a3a] leading-relaxed">{n.examTip}</p>
              </Block>
            </div>
          </article>
        ))}

        <p className="text-[12px] text-[#9a9a9a] leading-relaxed px-1">
          Today you learned how to solve linear equations. Before the exam, remember to move terms
          carefully, change signs correctly, expand brackets fully, and check your answer by
          substituting it back into the original equation.
        </p>
      </div>
    </PageShell>
  );
}

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="text-[10px] font-semibold tracking-widest uppercase text-[#9a9a9a] mb-2">{label}</div>
      {children}
    </section>
  );
}
