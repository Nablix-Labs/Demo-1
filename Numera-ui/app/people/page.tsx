'use client';

import type { ReactElement } from 'react';
import PageShell, { Chip } from '@/components/PageShell';
import { useStudentProfile } from '@/hooks/useStudentProfile';

export default function PeoplePage(): ReactElement {
  const { profile, loading, error, reload } = useStudentProfile();
  return <PageShell title="People" subtitle="Your assistant and the guardians connected to your account.">
    <div className="flex flex-col gap-9">
      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-blue">Your learning assistant</h2>
        <div className="rounded-xl border border-muted-gray bg-white p-4">
          <div className="flex items-center justify-between"><h3 className="font-semibold text-ink">Numera AI</h3><Chip tone="solid">AI assistant</Chip></div>
          <p className="mt-1 text-sm text-slate-blue">Your AI maths assistant.</p>
        </div>
      </section>
      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-blue">Responsible for you</h2>
        {loading && <p role="status">Loading your guardians…</p>}
        {error && <div role="alert" className="rounded-xl border border-action-orange p-4 text-sm">
          {error}<button onClick={reload} className="ml-3 underline">Retry</button>
        </div>}
        {profile && (profile.guardians.length === 0 ? <p className="text-sm text-slate-blue">No guardian linked to your account.</p> : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {profile.guardians.map((guardian) => <div key={guardian.guardian_id} className="rounded-xl border border-muted-gray bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-semibold text-ink">{guardian.name || 'Name not set'}</h3><Chip tone="outline">Guardian</Chip>
              </div>
              <p className="mt-1 text-sm text-slate-blue">{guardian.relationship || 'Relationship not set'}</p>
              <p className="mt-3 break-words text-sm text-ink">Email: {guardian.email || 'Not set'}</p>
              <p className="mt-1 text-sm text-ink">Phone: {guardian.phone || 'Not set'}</p>
              <p className="mt-3 text-xs text-slate-blue">{guardian.verified === null ? 'Verification not set' : guardian.verified ? 'Identity verified' : 'Identity not verified'}</p>
            </div>)}
          </div>
        ))}
      </section>
      <section><h2 className="mb-3 text-sm font-semibold text-slate-blue">Human tutors and study group</h2>
        <p className="text-sm text-slate-blue">Tutor and classmate connections are not available yet.</p>
      </section>
    </div>
  </PageShell>;
}
