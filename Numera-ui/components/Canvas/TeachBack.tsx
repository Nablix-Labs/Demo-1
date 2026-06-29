'use client';

/**
 * TeachBack — a "teaching back" moment inside guided learning. The tutor asks
 * the student to explain a step in their own words; articulating it is how the
 * understanding sticks. (The AI's response is mocked; backend would assess it.)
 */

import { useState } from 'react';
import { GraduationCap, X, Check } from 'lucide-react';

export default function TeachBack() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const close = () => { setOpen(false); setSubmitted(false); setText(''); };

  return (
    <div className="absolute top-[22px] right-[34px] z-20">
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className="flex items-center gap-1.5 rounded-full border border-[#9a9a9a] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1a1a1a] hover:bg-[#f4f4f4] transition-colors"
          style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}
        >
          <GraduationCap size={15} strokeWidth={1.8} /> Explain it back
        </button>
      ) : (
        <div className="w-[300px] bg-white border border-[#9a9a9a] rounded-xl overflow-hidden" style={{ boxShadow: '0 6px 22px rgba(0,0,0,0.16)' }}>
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#eaeaea]">
            <span className="flex items-center gap-1.5 text-[12.5px] font-semibold text-[#1a1a1a]">
              <GraduationCap size={15} strokeWidth={1.8} /> Teach it back
            </span>
            <button onClick={close} aria-label="Close" className="w-6 h-6 rounded-md flex items-center justify-center text-[#7a7a7a] hover:bg-[#f4f4f4]">
              <X size={15} strokeWidth={1.8} />
            </button>
          </div>
          <div className="p-4">
            {!submitted ? (
              <>
                <p className="text-[12.5px] text-[#7a7a7a] leading-snug mb-3">
                  In your own words — how would you explain the first step to a friend?
                </p>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={3}
                  placeholder="Type your explanation…"
                  className="w-full rounded-md border border-[#c8c8c8] px-3 py-2 text-[12.5px] outline-none focus:border-[#9a9a9a] resize-none"
                />
                <button
                  onClick={() => setSubmitted(true)}
                  disabled={!text.trim()}
                  className={
                    'mt-3 w-full rounded-md px-4 py-2 text-[12.5px] font-semibold transition-opacity ' +
                    (text.trim() ? 'bg-[#1a1a1a] text-white hover:opacity-80' : 'bg-[#eaeaea] text-[#9a9a9a]')
                  }
                >
                  Share with tutor
                </button>
              </>
            ) : (
              <div className="flex items-start gap-2.5">
                <span className="flex-shrink-0 mt-0.5 w-5 h-5 rounded-full bg-[#1a1a1a] text-white flex items-center justify-center">
                  <Check size={12} strokeWidth={2.4} />
                </span>
                <p className="text-[12.5px] text-[#1a1a1a] leading-snug">
                  Nice — explaining it back shows you really understand it. That&apos;s the goal.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
