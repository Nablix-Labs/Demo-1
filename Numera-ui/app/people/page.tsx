/**
 * People — everyone connected to the student's account.
 *
 * This was one flat list where a guardian, a classmate and the AI tutor all
 * carried the same weight, distinguished only by a chip at the end of the row.
 * They are grouped by relationship now, because that is how a student thinks
 * about them: the people who teach me, the people I work with, the people
 * responsible for me.
 *
 * It reuses the card grid from History and the Workbook so the library reads as
 * one thing, with the avatar in the slot where a Workbook card puts its
 * illustration — for a person, their face IS the picture.
 *
 * Cards are deliberately not clickable. There are no profile pages, and a card
 * that looks pressable but does nothing is worse than one that does not. The
 * only action here is the guardian's consent link, which is real.
 */

import Link from 'next/link';
import { ShieldCheck } from 'lucide-react';
import PageShell, { Chip } from '@/components/PageShell';

interface Person {
  name: string;
  role: 'Tutor' | 'Student' | 'Parent';
  detail: string;
  online: boolean;
  /** The AI tutor is not a person, and should not wear someone's initials. */
  ai?: boolean;
}

const PEOPLE: Person[] = [
  { name: 'Numera AI', role: 'Tutor', detail: 'Your AI maths tutor · always on', online: true, ai: true },
  { name: 'Ms Priya Sharma', role: 'Tutor', detail: 'Algebra & Number · human tutor', online: true },
  { name: 'Aïsha Khan', role: 'Student', detail: 'Year 9 · study group', online: true },
  { name: 'Liam OConnor', role: 'Student', detail: 'Year 9 · study group', online: false },
  { name: 'Wei Chen', role: 'Student', detail: 'Year 10 · study group', online: false },
  { name: 'Fatima Noor', role: 'Parent', detail: 'Guardian · progress reports', online: false },
];

/** Grouped the way a student thinks about them, not alphabetically. */
const GROUPS: { role: Person['role']; title: string; blurb: string }[] = [
  { role: 'Tutor', title: 'Who teaches you', blurb: 'Your tutors, human and AI.' },
  { role: 'Student', title: 'Your study group', blurb: 'Classmates working on the same topics.' },
  { role: 'Parent', title: 'Responsible for you', blurb: 'Guardians who receive your progress.' },
];

const initials = (name: string) =>
  name.split(' ').map((n) => n[0]).slice(0, 2).join('').toUpperCase();

export default function PeoplePage() {
  return (
    <PageShell
      title="People"
      subtitle="Tutors, classmates and guardians connected to your account."
    >
      <div className="flex flex-col gap-9">
        {GROUPS.map(({ role, title, blurb }) => {
          const people = PEOPLE.filter((p) => p.role === role);
          if (people.length === 0) return null;

          return (
            <section key={role}>
              <div className="mb-3">
                <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-blue">
                  {title}
                </h2>
                <p className="mt-1 text-[12px] text-slate-blue/80">{blurb}</p>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                {people.map((p) => (
                  <div
                    key={p.name}
                    className="flex flex-col rounded-xl border border-muted-gray bg-white p-4"
                  >
                    {/* Where a Workbook card puts its folder, a person puts their face. */}
                    <div className="flex items-center justify-center rounded-lg bg-reading-surface/70 px-4 py-7">
                      <span className="relative">
                        <span
                          className={
                            'flex h-16 w-16 items-center justify-center rounded-full text-[19px] font-semibold tracking-[0.5px] ' +
                            (p.ai
                              ? 'bg-ai-cyan text-white'
                              : 'border border-muted-gray bg-white text-ink')
                          }
                        >
                          {p.ai ? 'N' : initials(p.name)}
                        </span>
                        <span
                          className={
                            'absolute bottom-0.5 right-0.5 h-3.5 w-3.5 rounded-full border-2 border-white ' +
                            (p.online ? 'bg-success-sage' : 'bg-muted-gray')
                          }
                          aria-label={p.online ? 'Online' : 'Offline'}
                        />
                      </span>
                    </div>

                    <div className="mt-3 flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <h3 className="truncate text-[15px] font-semibold text-ink">{p.name}</h3>
                        <p className="mt-0.5 line-clamp-1 text-[11.5px] text-slate-blue">
                          {p.detail}
                        </p>
                      </div>
                      <Chip tone={p.role === 'Tutor' ? 'solid' : 'outline'}>{p.role}</Chip>
                    </div>

                    {/* The one real action on this page. */}
                    {p.role === 'Parent' && (
                      <Link
                        href="/consent/manage"
                        className="mt-3.5 inline-flex items-center justify-center gap-1.5 rounded-md border border-muted-gray px-3 py-2 text-[12px] font-semibold text-ink transition-colors hover:border-focus-navy"
                      >
                        <ShieldCheck size={14} strokeWidth={1.9} />
                        Manage consent
                      </Link>
                    )}
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </PageShell>
  );
}
