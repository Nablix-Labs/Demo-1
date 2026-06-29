'use client';

/**
 * Group Challenge Mode — collaborative room where every student works on their
 * own private canvas while the shared AI tutor observes all of them, runs the
 * shared board, and gives private feedback. (Mock-driven; real Group Session
 * Server plugs in behind the same store actions + collab interface.)
 */

import { useEffect, useRef, useState } from 'react';
import { Users, Copy, Check, LogOut, Sparkles, X, LayoutGrid, User } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useChallenge } from '@/hooks/useChallenge';
import PrivateCanvas from '@/components/Challenge/PrivateCanvas';
import SharedBoard from '@/components/Challenge/SharedBoard';
import AITutorBar from '@/components/Challenge/AITutorBar';
import TeacherView from '@/components/Challenge/TeacherView';

function initials(name: string) {
  return name.split(' ').map((n) => n[0]).slice(0, 2).join('').toUpperCase();
}

export default function ChallengePage() {
  useChallenge();
  const {
    challengeActive, challengeProblem, participants,
    privateFeedback, startChallenge, endChallenge, setPrivateFeedback,
  } = useNumeraStore();

  const [copied, setCopied] = useState(false);
  const [teacherView, setTeacherView] = useState(false);
  const fbTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-dismiss private feedback after a while
  useEffect(() => {
    if (!privateFeedback) return;
    fbTimer.current = setTimeout(() => setPrivateFeedback(null), 7000);
    return () => { if (fbTimer.current) clearTimeout(fbTimer.current); };
  }, [privateFeedback, setPrivateFeedback]);

  const link = 'numera.app/join/GROUP_123';
  const copy = async () => {
    try { await navigator.clipboard.writeText(link); } catch { /* ignore */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  // ── Intro / start ──
  if (!challengeActive) {
    return (
      <main className="flex-1 min-w-0 flex items-center justify-center bg-white p-8" aria-label="Group challenge">
        <div className="w-[420px] max-w-full text-center">
          <div className="w-12 h-12 mx-auto rounded-xl bg-[#1a1a1a] text-white flex items-center justify-center mb-4">
            <Users size={22} strokeWidth={1.8} />
          </div>
          <h1 className="text-[22px] font-semibold text-[#1a1a1a]">Group Challenge</h1>
          <p className="text-[13px] text-[#7a7a7a] mt-2 leading-relaxed">
            Solve together. Everyone works on their own private canvas while one shared AI tutor watches,
            spotlights great thinking, and coaches each of you.
          </p>
          <div className="mt-5 rounded-lg border border-[#c8c8c8] bg-[#f4f4f4] px-4 py-3 text-[15px] font-[Cambria_Math,Georgia,serif] text-[#1a1a1a]">
            Solve: {challengeProblem}
          </div>
          <button
            onClick={() => startChallenge(challengeProblem)}
            className="mt-5 w-full rounded-md bg-[#1a1a1a] text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity"
          >
            Start group challenge
          </button>
        </div>
      </main>
    );
  }

  // ── Active challenge ──
  return (
    <div className="flex-1 min-w-0 flex flex-col bg-white" aria-label="Group challenge room">
      {/* Header */}
      <header className="flex items-center gap-4 px-6 py-3.5 border-b border-[#c8c8c8] flex-shrink-0">
        <div className="min-w-0">
          <div className="text-[10px] tracking-widest uppercase text-[#9a9a9a]">Group challenge</div>
          <div className="text-[16px] font-semibold text-[#1a1a1a] font-[Cambria_Math,Georgia,serif]">
            Solve {challengeProblem}
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {/* Presence */}
          <div className="flex items-center -space-x-2">
            <span className="w-7 h-7 rounded-full border-2 border-white bg-[#1a1a1a] text-white flex items-center justify-center text-[10px] font-semibold" title="You">You</span>
            {participants.map((p) => (
              <span key={p.id} title={p.name} className="w-7 h-7 rounded-full border-2 border-white flex items-center justify-center text-[10px] font-semibold text-white" style={{ background: p.color }}>
                {initials(p.name)}
              </span>
            ))}
          </div>
          {/* Teacher/student view toggle (full visibility for supervision) */}
          <button
            onClick={() => setTeacherView((v) => !v)}
            title={teacherView ? 'Switch to your canvas' : 'Teacher view — see all canvases'}
            className="flex items-center gap-1.5 rounded-full border border-[#9a9a9a] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1a1a1a] hover:bg-[#f4f4f4] transition-colors"
          >
            {teacherView
              ? <><User size={14} strokeWidth={1.8} /> My canvas</>
              : <><LayoutGrid size={14} strokeWidth={1.8} /> Teacher view</>}
          </button>
          {/* Copy invite */}
          <button onClick={copy} className="flex items-center gap-1.5 rounded-full border border-[#9a9a9a] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1a1a1a] hover:bg-[#f4f4f4] transition-colors">
            {copied ? <><Check size={14} strokeWidth={2} /> Copied</> : <><Copy size={14} strokeWidth={1.8} /> Invite</>}
          </button>
          {/* Leave */}
          <button onClick={() => endChallenge()} className="flex items-center gap-1.5 rounded-full border border-[#c8c8c8] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#7a7a7a] hover:text-[#1a1a1a] hover:border-[#9a9a9a] transition-colors">
            <LogOut size={14} strokeWidth={1.8} /> Leave
          </button>
        </div>
      </header>

      {/* Body: private canvas (or teacher overview) + shared board */}
      <div className="flex-1 flex min-h-0 relative">
        {teacherView ? <TeacherView /> : <PrivateCanvas />}
        <SharedBoard />

        {/* Private feedback — only this student sees it */}
        {privateFeedback && (
          <div
            className="absolute bottom-5 left-6 z-30 max-w-sm flex items-start gap-3 bg-[#1a1a1a] text-white rounded-xl px-4 py-3"
            style={{ boxShadow: '0 6px 20px rgba(0,0,0,0.25)' }}
            role="status"
          >
            <Sparkles size={16} strokeWidth={1.8} className="flex-shrink-0 mt-0.5" />
            <div className="min-w-0">
              <div className="text-[10px] tracking-widest uppercase text-white/60 mb-0.5">Private feedback</div>
              <p className="text-[12.5px] leading-snug">{privateFeedback}</p>
            </div>
            <button onClick={() => setPrivateFeedback(null)} aria-label="Dismiss" className="flex-shrink-0 text-white/60 hover:text-white">
              <X size={15} strokeWidth={2} />
            </button>
          </div>
        )}
      </div>

      {/* Shared AI tutor voice + text bar */}
      <AITutorBar />
    </div>
  );
}
