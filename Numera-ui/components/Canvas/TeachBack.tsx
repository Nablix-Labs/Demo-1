'use client';

import { useState } from 'react';
import { GraduationCap, X } from 'lucide-react';

type TeachBackProps = {
  onSubmit: (text: string) => Promise<boolean>;
};

export default function TeachBack({ onSubmit }: TeachBackProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setOpen(false);
    setError(null);
    setText('');
  };

  const share = async () => {
    const explanation = text.trim();
    if (!explanation || sending) return;
    setSending(true);
    setError(null);
    const accepted = await onSubmit(explanation);
    setSending(false);
    if (accepted) {
      close();
      return;
    }
    setError("That didn't reach the tutor. Your explanation is still here — try once more.");
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
        <div className="w-[300px] overflow-hidden rounded-xl border border-muted-gray bg-white" style={{ boxShadow: '0 6px 22px rgba(0,0,0,0.16)' }}>
          <div className="flex items-center justify-between border-b border-muted-gray px-4 py-3">
            <span className="flex items-center gap-1.5 text-[12.5px] font-semibold text-ink">
              <GraduationCap size={15} strokeWidth={1.8} /> Teach it back
            </span>
            <button onClick={close} aria-label="Close" className="flex h-6 w-6 items-center justify-center rounded-md text-slate-blue hover:bg-reading-surface">
              <X size={15} strokeWidth={1.8} />
            </button>
          </div>
          <div className="p-4">
            <p className="mb-3 text-[12.5px] leading-snug text-slate-blue">
              In your own words — how would you explain the first step to a friend?
            </p>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={3}
              placeholder="Type your explanation…"
              disabled={sending}
              className="w-full resize-none rounded-md border border-muted-gray px-3 py-2 text-[12.5px] outline-none focus:border-ai-cyan disabled:opacity-60"
            />
            {error && <p role="alert" className="mt-2 text-[12px] text-action-orange">{error}</p>}
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
          </div>
        </div>
      )}
    </div>
  );
}
