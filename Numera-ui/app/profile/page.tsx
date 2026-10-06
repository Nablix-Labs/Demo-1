'use client';

/**
 * Profile — who the student is, how they learn, and what they have agreed to.
 *
 * Log out lives here rather than in the dock. A flat row of ten destinations
 * with "end my session" as the eleventh made a destructive action exactly as
 * easy to hit as Workbook; putting it behind a page you go to on purpose is the
 * whole reason this screen exists.
 *
 * The layout is a bento grid — a tall identity card beside a row of small
 * metric cards, one dark accent card, and a stack of disclosure sections. It is
 * recoloured to the Numera palette rather than the reference's cream and
 * yellow, because colour here still has to obey the brand rule that colour
 * always means something (see tailwind.config.ts).
 *
 * Identity and preferences come from the authenticated profile API.
 * Existing topic progress remains device-local and is labelled accordingly.
 */

import { useState } from 'react';
import type { FormEvent, ReactElement } from 'react';
import {
  ChevronDown, LogOut,
  Check, Stethoscope, Compass, GraduationCap, BookOpen, PenLine, RotateCcw,
} from 'lucide-react';
import PageShell from '@/components/PageShell';
import { cn } from '@/lib/cn';
import { useSignOut } from '@/hooks/useSignOut';
import {
  CONSENT_PURPOSES,
} from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useStudentProfile } from '@/hooks/useStudentProfile';
import type { AgeBand, GradeBand, PreferredMode, StudentProfile, StudentProfilePatch } from '@/lib/studentProfile';
import { PHASE_ORDER, PHASE_META } from '@/lib/phases';

/* ── Small primitives, local to this page ──────────────────────── */

function Card({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-muted-gray bg-white p-5 flex flex-col',
        className,
      )}
    >
      {children}
    </div>
  );
}

function CardLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold tracking-[0.9px] uppercase text-slate-blue">
      {children}
    </div>
  );
}

/** A value the backend has not supplied. Says so, rather than showing a zero
    that reads as a real measurement. */
function Unknown({ children }: { children: React.ReactNode }) {
  return <span className="text-slate-blue/60 font-normal">{children}</span>;
}

function Disclosure({
  title,
  meta,
  children,
  defaultOpen = false,
}: {
  title: string;
  meta?: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border border-muted-gray bg-white overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left hover:bg-reading-surface transition-colors"
      >
        <span className="text-[14px] font-semibold text-ink">{title}</span>
        <span className="flex items-center gap-3">
          {meta}
          <ChevronDown
            size={16}
            strokeWidth={2}
            className={cn('text-slate-blue transition-transform', open && 'rotate-180')}
          />
        </span>
      </button>
      {open && <div className="px-5 pb-5 pt-1 border-t border-muted-gray">{children}</div>}
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="py-2.5 flex items-baseline justify-between gap-6 border-b border-muted-gray/60 last:border-0">
      <span className="text-[12.5px] text-slate-blue flex-shrink-0">{label}</span>
      <span className="text-[13.5px] text-ink font-medium text-right break-words">{value}</span>
    </div>
  );
}

/* ── Page ──────────────────────────────────────────────────────── */

/**
 * The page's single accent. Flat, not a gradient.
 *
 * Deliberately one constant rather than scattered class names: this is the only
 * colour on the screen that is not already a brand token, so it needs exactly
 * one place to change. It is exposed to the markup as `--profile-accent` so
 * Tailwind classes and raw SVG strokes can both reach the same value.
 */
const GREEN = '#2ED47A';
/**
 * Text placed ON the green. The accent is a light neon, so white text on it
 * fails contrast badly (~1.6:1); ink gives ~8:1 and keeps the green bright.
 */
const ON_GREEN = '#12261C';

/** One glyph per phase, so the dark card is a list of six distinct things
    rather than the same icon repeated six times. */
const PHASE_ICON = {
  diagnostic:  Stethoscope,
  orientation: Compass,
  teach:       GraduationCap,
  workbook:    BookOpen,
  practice:    PenLine,
  review:      RotateCcw,
} as const;

/**
 * The status chip sits on the navy identity card, so the tone is a dot colour,
 * not a text colour. Tinted text (sage on navy) failed contrast badly enough to
 * be unreadable; white text with a coloured dot keeps the colour's meaning and
 * stays legible.
 */
const ACCOUNT_STATUS_COPY: Record<string, { label: string; dot: string }> = {
  active:                { label: 'Active',            dot: 'bg-success-sage' },
  consent_pending:       { label: 'Consent pending',   dot: 'bg-highlight-amber' },
  consent_withdrawn:     { label: 'Consent withdrawn', dot: 'bg-action-orange' },
  registration_started:  { label: 'Setting up',        dot: 'bg-muted-gray' },
  suspended:             { label: 'Suspended',         dot: 'bg-action-orange' },
  locked:                { label: 'Locked',            dot: 'bg-action-orange' },
  deleted:               { label: 'Deleted',           dot: 'bg-muted-gray' },
};

const AGE_BANDS: AgeBand[] = ['11–14 (KS3)', '14–16 (KS4)'];
const GRADES: GradeBand[] = ['Year 7', 'Year 8', 'Year 9', 'Year 10', 'Year 11'];
const MODES: PreferredMode[] = ['voice', 'text', 'balanced'];
const INPUT_CLASS = 'mt-1 w-full rounded-lg border border-muted-gray bg-white px-3 py-2 text-sm text-ink disabled:opacity-60';

function ProfileEditor({ profile, saving, save }: {
  profile: StudentProfile;
  saving: boolean;
  save: (changes: StudentProfilePatch) => Promise<StudentProfile>;
}): ReactElement {
  const [name, setName] = useState(profile.display_name ?? '');
  const [age, setAge] = useState<AgeBand | ''>(profile.age_band ?? '');
  const [grade, setGrade] = useState<GradeBand | ''>(profile.grade_band ?? '');
  const [mode, setMode] = useState<PreferredMode | ''>(profile.preferred_mode ?? '');
  const [inputMode, setInputMode] = useState<'voice' | 'text' | ''>(profile.preferences.input_mode ?? '');
  const [panelSide, setPanelSide] = useState<'left' | 'right' | ''>(profile.preferences.panel_side ?? '');
  const [message, setMessage] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setMessage(null);
    const preferences = {
      ...(inputMode && inputMode !== profile.preferences.input_mode ? { input_mode: inputMode } : {}),
      ...(panelSide && panelSide !== profile.preferences.panel_side ? { panel_side: panelSide } : {}),
    };
    const changes: StudentProfilePatch = {
      ...(name.trim() !== (profile.display_name ?? '') ? { display_name: name.trim() } : {}),
      ...(age && age !== profile.age_band ? { age_band: age } : {}),
      ...((grade || null) !== profile.grade_band ? { grade_band: grade || null } : {}),
      ...(mode && mode !== profile.preferred_mode ? { preferred_mode: mode } : {}),
      ...(Object.keys(preferences).length > 0 ? { preferences } : {}),
    };
    if (Object.keys(changes).length === 0) { setMessage('No changes to save.'); return; }
    try {
      const saved = await save(changes);
      setName(saved.display_name ?? '');
      setAge(saved.age_band ?? '');
      setGrade(saved.grade_band ?? '');
      setMode(saved.preferred_mode ?? '');
      setInputMode(saved.preferences.input_mode ?? '');
      setPanelSide(saved.preferences.panel_side ?? '');
      setMessage('Profile saved.');
    } catch {
      // useStudentProfile presents the error and retains the confirmed profile.
      setMessage(null);
    }
  };

  return <form onSubmit={(event) => { void submit(event); }}>
    <fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2">
      <legend className="sr-only">Edit your profile</legend>
      <label className="text-sm text-slate-blue">Display name
        <input name="display_name" value={name} maxLength={100} required className={INPUT_CLASS}
          onChange={(event) => setName(event.target.value)} autoComplete="name" />
      </label>
      <label className="text-sm text-slate-blue">Age band
        <select name="age_band" value={age} className={INPUT_CLASS} onChange={(event) => setAge(event.target.value as AgeBand | '')}>
          <option value="" disabled>Not set</option>{AGE_BANDS.map((value) => <option key={value}>{value}</option>)}
        </select>
      </label>
      <label className="text-sm text-slate-blue">Year group
        <select name="grade_band" value={grade} className={INPUT_CLASS} onChange={(event) => setGrade(event.target.value as GradeBand | '')}>
          <option value="">Not set</option>{GRADES.map((value) => <option key={value}>{value}</option>)}
        </select>
      </label>
      <label className="text-sm text-slate-blue">Preferred mode
        <select name="preferred_mode" value={mode} className={INPUT_CLASS} onChange={(event) => setMode(event.target.value as PreferredMode | '')}>
          <option value="" disabled>Not set</option>{MODES.map((value) => <option key={value}>{value}</option>)}
        </select>
      </label>
      <label className="text-sm text-slate-blue">Tutor input
        <select name="input_mode" value={inputMode} className={INPUT_CLASS} onChange={(event) => setInputMode(event.target.value as 'voice' | 'text' | '')}>
          <option value="" disabled>Not set</option><option value="voice">Voice</option><option value="text">Text</option>
        </select>
      </label>
      <label className="text-sm text-slate-blue">Tutor panel side
        <select name="panel_side" value={panelSide} className={INPUT_CLASS} onChange={(event) => setPanelSide(event.target.value as 'left' | 'right' | '')}>
          <option value="" disabled>Not set</option><option value="left">Left</option><option value="right">Right</option>
        </select>
      </label>
    </fieldset>
    <button type="submit" disabled={saving} className="mt-5 rounded-xl bg-focus-navy px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">
      {saving ? 'Saving…' : 'Save profile'}
    </button>
    {message && <p role="status" className="mt-3 text-sm text-slate-blue">{message}</p>}
  </form>;
}

export default function ProfilePage() {
  const { profile, loading, saving, error, reload, save } = useStudentProfile();
  const { signOut, signingOut, overlay } = useSignOut();
  const phasesDone = useNumeraStore((state) => state.phasesDone);
  if (!profile) return (
    <PageShell title="Your profile" subtitle="Your account, how you learn, and what you have agreed to." wide>
      {overlay}
      {loading && <p role="status">Loading your profile…</p>}
      {error && <p role="alert">{error} <button onClick={reload} className="underline">Retry</button></p>}
      <button onClick={signOut} disabled={signingOut} className="mt-4 underline">Log out</button>
    </PageShell>
  );
  const student = {
    name: profile.display_name, avatar: profile.avatar_url,
    ageBand: profile.age_band, gradeBand: profile.grade_band, preferredMode: profile.preferred_mode,
  };
  const email = profile.email;
  const tier = profile.tier;
  const studentCode = profile.student_code;
  const accountStatus = profile.account_status;
  const initials =
    (student.name || email || 'N')
      .split(/[\s@._]/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join('') || 'N';

  const done = PHASE_ORDER.filter((p) => phasesDone.includes(p)).length;
  const pct = Math.round((done / PHASE_ORDER.length) * 100);

  const activeConsents = profile.consents?.filter((record) => record.accepted_at && !record.withdrawn_at).length;
  const status = ACCOUNT_STATUS_COPY[accountStatus];
  const fields = [student.name, student.avatar, student.gradeBand, student.ageBand, email];
  const setupPct = Math.round(fields.filter(Boolean).length / fields.length * 100);

  return (
    <PageShell
      title={student.name ? `Welcome in, ${student.name.split(' ')[0]}` : 'Your profile'}
      subtitle="Your account, how you learn, and what you have agreed to."
      wide
    >
      {overlay}
      {error && <p role="alert" className="mb-4 text-action-orange">{error}</p>}

      <div style={{ '--profile-accent': GREEN } as React.CSSProperties}>

        {/* ── Header strip: segmented phase pills on the left, oversized
               counters on the right. The reference's top row, but every segment
               is a real phase from PHASE_ORDER — a filled pill means that phase
               is genuinely unlocked in the store, not decoration. ── */}
        <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-6 mb-5">
          <div className="flex items-end gap-2 flex-wrap">
            {PHASE_ORDER.map((p) => {
              const complete = phasesDone.includes(p);
              return (
                <div key={p}>
                  <div className="text-[10.5px] text-slate-blue mb-1.5 truncate max-w-[92px]">
                    {PHASE_META[p].label}
                  </div>
                  <div
                    className={cn(
                      'h-8 min-w-[74px] rounded-full flex items-center justify-center px-3 text-[11px] font-semibold',
                      !complete && 'bg-reading-surface text-slate-blue/70 border border-muted-gray',
                    )}
                    style={complete ? { background: GREEN, color: ON_GREEN } : undefined}
                  >
                    {complete ? 'Done' : 'Locked'}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-start gap-8">
            <Stat value={done} sub={`of ${PHASE_ORDER.length}`} label="Phases on this device" />
            <Stat value={activeConsents ?? "Not set"} label="Permissions" />
            <Stat value={`${setupPct}%`} label="Profile set up" />
          </div>
        </div>

        {/* ── Bento ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-12 gap-4">

          {/* Photo. Fills the card edge to edge with the name over a scrim,
              exactly as the reference does — a small circular avatar floating
              in the middle read as a placeholder, not a portrait. */}
          <div className="xl:col-span-3 relative rounded-2xl overflow-hidden min-h-[330px] flex flex-col">
            {student.avatar ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={student.avatar} alt="" className="absolute inset-0 w-full h-full object-cover" />
                {/* Scrim. Without it the name is unreadable over a light photo. */}
                <div
                  className="absolute inset-0"
                  style={{ background: 'linear-gradient(to top, rgba(11,16,32,0.85) 0%, rgba(11,16,32,0.25) 42%, transparent 68%)' }}
                  aria-hidden="true"
                />
              </>
            ) : (
              <div className="absolute inset-0" style={{ background: GREEN }} aria-hidden="true" />
            )}

            <div className="relative z-20 flex flex-1 flex-col items-center justify-center gap-3 p-5">
              {!student.avatar && <span className="text-3xl font-semibold" style={{ color: ON_GREEN }}>{initials}</span>}
              <span className="rounded-lg bg-white/90 px-3 py-2 text-xs text-ink">Photo changes are not available yet.</span>
            </div>

            {/* Name plate, over the scrim. */}
            {/* Name plate. pointer-events-none so it cannot steal the click
                from the upload label sitting underneath it. */}
            <div className="relative z-20 mt-auto p-5 pointer-events-none">
              <div
                className="text-[17px] font-semibold leading-tight truncate"
                style={{ color: student.avatar ? '#fff' : ON_GREEN }}
              >
                {student.name || <span className="font-normal opacity-60">Name not set</span>}
              </div>
              <div
                className="text-[11.5px] mt-0.5 truncate"
                style={{ color: student.avatar ? 'rgba(255,255,255,0.72)' : ON_GREEN, opacity: student.avatar ? 1 : 0.7 }}
              >
                {student.gradeBand || student.ageBand || 'Year group not set'}
              </div>
            </div>


          </div>

          {/* Progress — the reference's bar chart. One bar per phase; a full
              bar is an unlocked phase. */}
          <Card className="xl:col-span-3 min-h-[330px]">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[16px] font-semibold text-ink">Progress</div>
                <div className="text-[11.5px] text-slate-blue mt-0.5">Through this topic · on this device</div>
              </div>
              <span
                className="rounded-full px-2.5 py-1 text-[11px] font-semibold"
                style={{ background: GREEN, color: ON_GREEN }}
              >
                {done}/{PHASE_ORDER.length}
              </span>
            </div>

            {/* Bar heights are in pixels, not percentages. A percentage height
                resolves against the parent's *definite* height, and this row is
                a flex item with height:auto — so every bar computed to 0 and
                the chart rendered as six invisible columns. */}
            <div className="flex-1 flex items-end gap-2.5 pt-6 pb-1 min-h-[168px]">
              {PHASE_ORDER.map((p) => {
                const complete = phasesDone.includes(p);
                return (
                  <div
                    key={p}
                    className="flex-1 flex flex-col items-center justify-end gap-2"
                    title={PHASE_META[p].label}
                  >
                    {/* Capped width — a full-width bar in a 6-column flex row
                        reads as a stack of pills, not a chart. */}
                    <div
                      className={cn('w-full max-w-[26px] rounded-full', !complete && 'bg-muted-gray')}
                      style={{
                        height: complete ? 132 : 30,
                        background: complete ? GREEN : undefined,
                      }}
                    />
                    <span className="text-[10px] text-slate-blue uppercase">
                      {PHASE_META[p].label.slice(0, 1)}
                    </span>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Topic progress ring — the reference's time tracker dial. */}
          <Card className="xl:col-span-3 min-h-[330px] items-center">
            <div className="w-full flex items-start justify-between">
              <div className="text-[16px] font-semibold text-ink">Topic progress</div>
            </div>
            <div className="flex-1 flex items-center justify-center">
              <div className="relative w-[150px] h-[150px]">
                <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
                  <circle cx="60" cy="60" r="52" fill="none" stroke="#E0E2E5" strokeWidth="11" />
                  <circle
                    cx="60" cy="60" r="52" fill="none"
                    stroke={GREEN} strokeWidth="11" strokeLinecap="round"
                    strokeDasharray={`${(pct / 100) * 2 * Math.PI * 52} ${2 * Math.PI * 52}`}
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-[30px] font-semibold text-ink leading-none tabular-nums">{pct}%</span>
                  <span className="text-[10.5px] text-slate-blue mt-1.5">unlocked</span>
                </div>
              </div>
            </div>
            <div className="text-[11.5px] text-slate-blue w-full">
              {done === PHASE_ORDER.length
                ? 'Every phase of this topic is open.'
                : `Next up: ${PHASE_META[PHASE_ORDER.find((p) => !phasesDone.includes(p))!].label}.`}
            </div>
          </Card>

          {/* The dark card, spanning two rows as in the reference. Its task
              list is the six real phases with their genuine unlocked state. */}
          <div
            className="xl:col-span-3 xl:row-span-2 rounded-2xl p-5 flex flex-col"
            style={{ background: GREEN, color: ON_GREEN }}
          >
            <div className="flex items-start justify-between">
              <div className="text-[15px] font-semibold">Learning flow · on this device</div>
              <div className="text-[15px] font-semibold tabular-nums">
                {done}<span className="opacity-50">/{PHASE_ORDER.length}</span>
              </div>
            </div>

            <div className="mt-5 space-y-2.5 flex-1">
              {PHASE_ORDER.map((p) => {
                const complete = phasesDone.includes(p);
                const Icon = PHASE_ICON[p];
                return (
                  <div
                    key={p}
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5"
                    style={{ background: 'rgba(255,255,255,0.55)' }}
                  >
                    <span
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: 'rgba(0,0,0,0.07)' }}
                    >
                      <Icon size={14} strokeWidth={1.8} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[12.5px] font-semibold truncate">
                        {PHASE_META[p].label}
                      </div>
                      <div className="text-[10.5px] opacity-60 truncate">
                        {complete ? 'Unlocked' : 'Locked'}
                      </div>
                    </div>
                    {/* On a green card the tick has to be dark-on-white, not
                        green-on-green — a green tick vanished into the card. */}
                    <span
                      className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
                      style={
                        complete
                          ? { background: ON_GREEN }
                          : { border: '1px solid rgba(0,0,0,0.22)' }
                      }
                      aria-hidden="true"
                    >
                      {complete && <Check size={12} strokeWidth={3} style={{ color: GREEN }} />}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Accordions — the reference's left-hand disclosure stack. */}
          <div className="xl:col-span-3 space-y-3">
            <Disclosure title="Guardians" defaultOpen={true}>
              {profile.guardians.length === 0 ? <p className="text-sm text-slate-blue">No guardian linked to your account.</p> : profile.guardians.map((guardian) => (
                <div key={guardian.guardian_id} className="mb-4 last:mb-0">
                  <Field label="Name" value={guardian.name || <Unknown>Not set</Unknown>} />
                  <Field label="Relationship" value={guardian.relationship || <Unknown>Not set</Unknown>} />
                  <Field label="Email" value={guardian.email || <Unknown>Not set</Unknown>} />
                  <Field label="Phone" value={guardian.phone || <Unknown>Not set</Unknown>} />
                  <Field label="Identity verified" value={guardian.verified === null ? <Unknown>Not set</Unknown> : guardian.verified ? 'Verified' : 'Not verified'} />
                </div>
              ))}
              <p className="mt-3 text-xs text-slate-blue">Guardian details are read-only.</p>
            </Disclosure>

            <Disclosure title="Account">
              <Field label="Email" value={email || <Unknown>Not set</Unknown>} />
              <Field label="Student code" value={studentCode || <Unknown>Not issued yet</Unknown>} />
              <Field label="Plan" value={tier || <Unknown>Not set</Unknown>} />
              <Field label="Age band" value={student.ageBand || <Unknown>Not set</Unknown>} />
            </Disclosure>

            <Disclosure title="Privacy & permissions" defaultOpen={true}>
              <p className="py-3 text-xs text-slate-blue">Permissions are read-only. Consent changes are not available in this release.</p>
              {CONSENT_PURPOSES.map((purpose) => {
                const consent = profile.consents?.find((record) => record.purpose === purpose.id);
                const value = !consent ? 'Not set' : consent.withdrawn_at ? 'Withdrawn' : consent.accepted_at ? 'Granted' : 'Not granted';
                return <Field key={purpose.id} label={purpose.label} value={value} />;
              })}
            </Disclosure>
          </div>

          {/* How you learn — real, writable settings that drive the lesson. */}
          <Card className="xl:col-span-6">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[16px] font-semibold text-ink">How you learn</div>
                <div className="text-[11.5px] text-slate-blue mt-0.5">
                  Takes effect on your next lesson screen.
                </div>
              </div>
              <span className="rounded-full bg-reading-surface text-slate-blue px-2.5 py-1 text-[10px] font-semibold tracking-[0.4px] uppercase">
                {student.preferredMode || 'not set'}
              </span>
            </div>

            <div className="mt-6">
              <ProfileEditor key={profile.student_id} profile={profile} saving={saving} save={save} />
            </div>

            {/* Log out lives at the bottom of the profile, not in the dock. */}
            <div className="mt-6 pt-5 border-t border-muted-gray flex items-center justify-between gap-5 flex-wrap">
              <div className="min-w-0">
                <div className="text-[13.5px] font-semibold text-ink">Log out</div>
                <p className="text-[11.5px] text-slate-blue mt-0.5 leading-snug">
                  Ends this tutoring session and clears your progress from this device.
                </p>
              </div>
              <button
                onClick={signOut}
                disabled={signingOut}
                className={cn(
                  'flex-shrink-0 flex items-center gap-2 rounded-xl border px-4 py-2.5 text-[13px] font-semibold transition-colors',
                  'border-action-orange/40 text-action-orange hover:bg-action-orange hover:text-white',
                  'disabled:opacity-50 disabled:pointer-events-none',
                )}
              >
                <LogOut size={15} strokeWidth={2} />
                {signingOut ? 'Signing out…' : 'Log out'}
              </button>
            </div>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}

/** Oversized counter, as in the reference's 78 / 56 / 203 row. */
function Stat({ value, sub, label }: { value: React.ReactNode; sub?: string; label: string }) {
  return (
    <div>
      <div className="text-[36px] leading-none font-semibold text-ink tabular-nums">
        {value}
        {sub && <span className="text-[16px] text-slate-blue ml-1">{sub}</span>}
      </div>
      <div className="text-[11px] text-slate-blue mt-2">{label}</div>
    </div>
  );
}
