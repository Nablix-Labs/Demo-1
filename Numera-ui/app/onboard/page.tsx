'use client';

/**
 * Onboarding — the entry point. A minimal registration mock: name + start.
 * On continue it sends the student into the one-time Main Diagnostic, which
 * places them at their starting topic (see docs/LEARNING-FLOW.md).
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useNumeraStore } from '@/store/useNumeraStore';

export default function OnboardPage() {
  const router = useRouter();
  const setStudentName = useNumeraStore((s) => s.setStudentName);
  const [name, setName] = useState('');

  const start = () => {
    setStudentName(name.trim());
    router.push('/diagnostic');
  };

  return (
    <main className="flex-1 min-w-0 flex items-center justify-center bg-white p-8" aria-label="Welcome">
      <div className="w-[460px] max-w-full">
        <div className="text-[10px] tracking-widest uppercase text-[#9a9a9a] mb-2">Welcome to Numera</div>
        <h1 className="text-[24px] font-semibold text-[#1a1a1a] leading-tight">
          Let&apos;s get you set up
        </h1>
        <p className="text-[13px] text-[#7a7a7a] mt-2 leading-relaxed">
          First we&apos;ll run a one-time diagnostic to find your level and start you at
          the right topic. It only takes a few minutes.
        </p>

        <label className="block mt-6 text-[12px] font-semibold text-[#1a1a1a]">
          What should we call you?
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && name.trim() && start()}
            placeholder="Your name"
            className="mt-1.5 w-full rounded-md border border-[#c8c8c8] bg-white px-3.5 py-2.5 text-[14px] text-[#1a1a1a] placeholder:text-[#9a9a9a] focus:border-[#1a1a1a] focus:outline-none transition-colors"
          />
        </label>

        <button
          onClick={start}
          disabled={name.trim().length === 0}
          className="mt-5 w-full rounded-md bg-[#1a1a1a] text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 disabled:opacity-30 disabled:cursor-not-allowed transition-opacity"
        >
          Start diagnostic
        </button>
      </div>
    </main>
  );
}
