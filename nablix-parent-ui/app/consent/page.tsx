'use client';

import { useState } from 'react';
import { ShieldCheck, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';
import Shell from '@/components/Shell';
import { Card, PageHeader, Pill, dateLabel } from '@/components/ui';
import { setConsent, isSample } from '@/lib/api';
import { useChild } from '@/lib/useChild';
import type { ChildData, ConsentPurpose } from '@/lib/types';

export default function ConsentPage() {
  return <Shell>{(d) => <Consent d={d} />}</Shell>;
}

/** Same purposes and wording as the student app's consent screen. */
const PURPOSES: { id: ConsentPurpose; label: string; detail: string; mandatory: boolean }[] = [
  { id: 'account_creation', label: 'Account creation', detail: 'Create and manage the student account.', mandatory: true },
  { id: 'ai_tutor_usage', label: 'AI tutor usage', detail: 'Let your child learn with the AI maths tutor.', mandatory: true },
  { id: 'canvas_processing', label: 'Canvas processing', detail: 'Read and give feedback on written working on the canvas.', mandatory: true },
  { id: 'voice_processing', label: 'Voice processing', detail: 'Enable voice input and voice-based tutoring.', mandatory: true },
  { id: 'learning_analytics', label: 'Learning analytics', detail: 'Store progress, session history and feedback — what this portal shows.', mandatory: true },
  { id: 'safety_monitoring', label: 'Safety monitoring', detail: 'Apply safeguarding rules to your child’s conversations.', mandatory: true },
  { id: 'marketing', label: 'Product updates', detail: 'Occasional news about Numera. Optional, off by default.', mandatory: false },
];

function Consent({ d }: { d: ChildData }) {
  const { touch } = useChild();
  const first = d.child.name.split(' ')[0];
  const [confirm, setConfirm] = useState<ConsentPurpose | null>(null);
  const [busy, setBusy] = useState<ConsentPurpose | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rec = (p: ConsentPurpose) => d.consents.find((c) => c.purpose === p);
  const active = (p: ConsentPurpose) => Boolean(rec(p)?.accepted_at && !rec(p)?.withdrawn_at);
  const paused = PURPOSES.some((p) => p.mandatory && !active(p.id));

  const apply = async (p: ConsentPurpose, granted: boolean) => {
    setBusy(p);
    setError(null);
    try {
      const updated = await setConsent(d.child.student_code, p, granted);
      Object.assign(rec(p) ?? {}, updated);
      touch();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That change was not saved.');
    } finally {
      setBusy(null);
      setConfirm(null);
    }
  };

  return (
    <>
      <PageHeader title="Consent & privacy" subtitle={`What you have agreed to for ${first}'s account. You can change these at any time.`} />

      {paused && (
        <div className="mb-4 flex items-start gap-2.5 rounded-[18px] border border-coral bg-coral-soft/50 px-4 py-3 text-[13px] text-ink">
          <AlertTriangle size={17} className="mt-0.5 flex-shrink-0 text-coral" aria-hidden />
          <span><b>{first}&apos;s account is paused.</b> A required consent has been withdrawn, so {first} cannot start lessons until it is given again.</span>
        </div>
      )}
      {error && <p className="mb-4 rounded-[18px] bg-coral-soft px-4 py-3 text-[13px] text-[#B5334F]">{error}</p>}

      <Card title="Permissions" icon={<ShieldCheck size={18} />}>
        <ul className="flex flex-col divide-y divide-line">
          {PURPOSES.map((p) => {
            const on = active(p.id);
            const r = rec(p.id);
            return (
              <li key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3.5">
                <span className="min-w-[220px] flex-1">
                  <span className="flex items-center gap-2 text-[13.5px] font-extrabold text-ink">
                    {p.label} {p.mandatory && <span className="text-[11px] font-normal text-ink-soft">Required</span>}
                  </span>
                  <span className="mt-0.5 block text-[12.5px] text-ink-soft">{p.detail}</span>
                  {r?.withdrawn_at ? (
                    <span className="mt-0.5 block text-[11.5px] text-ink-soft">Withdrawn {dateLabel(r.withdrawn_at, { day: 'numeric', month: 'long' })}</span>
                  ) : r?.accepted_at ? (
                    <span className="mt-0.5 block text-[11.5px] text-ink-soft">Given {dateLabel(r.accepted_at, { day: 'numeric', month: 'long', year: 'numeric' })}</span>
                  ) : null}
                </span>
                <Pill tone={on ? 'good' : p.mandatory ? 'bad' : 'neutral'}>{on ? 'On' : 'Off'}</Pill>
                {confirm === p.id ? (
                  <span className="flex items-center gap-2">
                    <span className="text-[12px] text-[#B5334F]">This pauses {first}&apos;s lessons.</span>
                    <button onClick={() => apply(p.id, false)} disabled={busy !== null} className="rounded-lg bg-coral px-3 py-1.5 text-[12px] font-extrabold text-white disabled:opacity-60">
                      Withdraw
                    </button>
                    <button onClick={() => setConfirm(null)} className="rounded-lg border border-line px-3 py-1.5 text-[12px] font-extrabold text-ink">
                      Keep
                    </button>
                  </span>
                ) : (
                  <button
                    disabled={busy !== null}
                    onClick={() => (on && p.mandatory ? setConfirm(p.id) : apply(p.id, !on))}
                    className={clsx(
                      'w-[96px] rounded-lg border px-3 py-1.5 text-[12px] font-extrabold disabled:opacity-60',
                      on ? 'border-line text-ink hover:bg-cream-deep' : 'border-ink bg-ink text-white',
                    )}
                  >
                    {busy === p.id ? 'Saving…' : on ? 'Withdraw' : 'Give consent'}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        {isSample && (
          <p className="mt-3 text-[12px] text-ink-soft">Sample data: changes here last until you close the tab.</p>
        )}
      </Card>

      <Card title="Your child's data" className="mt-4">
        <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[13px] text-ink">
          <li>Numera keeps {first}&apos;s answers, written working and voice transcripts to tutor them and to show you progress here.</li>
          <li>Withdrawing a required consent pauses the account. It does not delete anything.</li>
          <li>To ask for a copy of {first}&apos;s data or to delete the account, email <a className="font-extrabold text-teal-deep" href="mailto:privacy@nablix.ai">privacy@nablix.ai</a>.</li>
        </ul>
      </Card>
    </>
  );
}
