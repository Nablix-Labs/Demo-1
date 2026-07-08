'use client';

/**
 * Right panel of the challenge room. Two tabs:
 *  - Board: the AI-controlled shared board (commentary + spotlight).
 *  - Chat:  student-to-student group chat, which unlocks only after the
 *           student has done a guided lesson AND a practice.
 */

import { useState } from 'react';
import { Check, AlertCircle, Sparkles, Radio, MessagesSquare, Lock, ArrowUp } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';
import { uid } from '@/lib/uid';

interface ChatMsg { id: string; author: string; color: string; text: string; you?: boolean }

const SEED_CHAT: ChatMsg[] = [
  { id: 'c1', author: 'Aïsha', color: '#2563eb', text: 'wait do we subtract 5 first?' },
  { id: 'c2', author: 'Liam', color: '#d97706', text: 'yeah then divide by 3' },
  { id: 'c3', author: 'Wei', color: '#0d9488', text: 'got x = 5, nice' },
];

export default function SharedBoard() {
  const commentary = useNumeraStore((s) => s.commentary);
  const spotlight = useNumeraStore((s) => s.spotlight);
  const completedLessons = useNumeraStore((s) => s.completedLessons);
  const practiceCompleted = useNumeraStore((s) => s.practiceCompleted);

  const [tab, setTab] = useState<'board' | 'chat'>('board');
  const chatUnlocked = completedLessons.length > 0 && practiceCompleted;

  return (
    <aside className="flex-shrink-0 w-[320px] border-l border-muted-gray bg-white flex flex-col min-h-0" aria-label="Shared board and chat">
      {/* Tabs */}
      <div className="flex items-stretch border-b border-muted-gray flex-shrink-0">
        <TabBtn active={tab === 'board'} onClick={() => setTab('board')} icon={<Radio size={15} strokeWidth={1.8} />} label="Board" />
        <TabBtn active={tab === 'chat'} onClick={() => setTab('chat')} icon={<MessagesSquare size={15} strokeWidth={1.8} />} label="Chat" locked={!chatUnlocked} />
      </div>

      {tab === 'board' ? (
        <BoardContent commentary={commentary} spotlight={spotlight} />
      ) : chatUnlocked ? (
        <ChatContent />
      ) : (
        <LockedChat />
      )}
    </aside>
  );
}

function TabBtn({ active, onClick, icon, label, locked }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string; locked?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex-1 flex items-center justify-center gap-1.5 py-3 text-[12px] font-semibold transition-colors border-b-2',
        active ? 'border-focus-navy text-ink' : 'border-transparent text-slate-blue hover:text-ink'
      )}
    >
      {icon} {label} {locked && <Lock size={11} strokeWidth={2} />}
    </button>
  );
}

function BoardContent({ commentary, spotlight }: { commentary: ReturnType<typeof useNumeraStore.getState>['commentary']; spotlight: ReturnType<typeof useNumeraStore.getState>['spotlight'] }) {
  return (
    <>
      <div className="flex items-center gap-2 px-5 py-3 border-b border-muted-gray flex-shrink-0">
        <span className="text-[10px] tracking-widest uppercase text-slate-blue">AI-led shared board</span>
      </div>
      {spotlight && (
        <div className="px-5 py-4 border-b border-muted-gray">
          <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2">On the board</div>
          <div className={cn('rounded-lg border p-3.5', spotlight.kind === 'good' && 'border-focus-navy bg-reading-surface', spotlight.kind === 'mistake' && 'border-dashed border-muted-gray bg-white', spotlight.kind === 'solution' && 'border-focus-navy bg-white')}>
            <div className="flex items-center gap-2 mb-1.5">
              {spotlight.kind === 'good' && <Check size={15} strokeWidth={2} className="text-ink" />}
              {spotlight.kind === 'mistake' && <AlertCircle size={15} strokeWidth={1.8} className="text-slate-blue" />}
              {spotlight.kind === 'solution' && <Sparkles size={15} strokeWidth={1.8} className="text-ink" />}
              <span className="text-[11px] font-semibold tracking-wide uppercase text-slate-blue">
                {spotlight.kind === 'good' ? 'Good work' : spotlight.kind === 'mistake' ? 'Learning moment' : 'Solution step'}
                {spotlight.studentName ? ` · ${spotlight.studentName}` : spotlight.kind === 'mistake' ? ' · anonymous' : ''}
              </span>
            </div>
            <p className="text-[12.5px] text-ink leading-snug">{spotlight.caption}</p>
          </div>
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
        <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-3">Live commentary</div>
        {commentary.length === 0 ? (
          <p className="text-[12px] text-slate-blue">The tutor will comment as the group works…</p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {commentary.map((c) => (
              <div key={c.id} className="flex items-start gap-2.5">
                <span className="flex-shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full bg-focus-navy" />
                <p className="text-[12.5px] text-ink leading-snug">
                  {c.text}
                  {c.tone === 'hint' && <span className="ml-1 text-[10px] tracking-wide uppercase text-slate-blue">hint</span>}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function ChatContent() {
  const [messages, setMessages] = useState<ChatMsg[]>(SEED_CHAT);
  const [text, setText] = useState('');
  const send = () => {
    const t = text.trim();
    if (!t) return;
    setMessages((m) => [...m, { id: uid(), author: 'You', color: '#4169E1', text: t, you: true }]);
    setText('');
  };
  return (
    <>
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        {messages.map((m) => (
          <div key={m.id} className={cn('flex flex-col', m.you && 'items-end')}>
            <span className="text-[10px] font-semibold mb-0.5" style={{ color: m.color }}>{m.author}</span>
            <span className={cn('inline-block max-w-[85%] rounded-lg px-3 py-1.5 text-[12.5px]', m.you ? 'bg-focus-navy text-white' : 'bg-reading-surface text-ink')}>
              {m.text}
            </span>
          </div>
        ))}
      </div>
      <div className="flex-shrink-0 border-t border-muted-gray p-3 flex items-center gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Message the group…"
          aria-label="Group chat message"
          className="flex-1 rounded-full border border-muted-gray px-3.5 py-2 text-[12.5px] outline-none"
        />
        <button onClick={send} disabled={!text.trim()} aria-label="Send" className={cn('w-8 h-8 rounded-full flex items-center justify-center', text.trim() ? 'bg-focus-navy text-white' : 'bg-reading-surface text-slate-blue')}>
          <ArrowUp size={15} strokeWidth={2} />
        </button>
      </div>
    </>
  );
}

function LockedChat() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-8">
      <div className="w-10 h-10 rounded-full bg-reading-surface border border-muted-gray flex items-center justify-center mb-3">
        <Lock size={17} strokeWidth={1.8} className="text-slate-blue" />
      </div>
      <div className="text-[13px] font-semibold text-ink">Group chat is locked</div>
      <p className="text-[12px] text-slate-blue mt-1.5 leading-snug">
        Finish a guided lesson and an independent practice to unlock chatting with your group.
      </p>
    </div>
  );
}
