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
 * Everything on this page reads from the real stores. Nothing is invented: if
 * the backend has not sent a value, the card says so instead of showing a
 * plausible number.
 */

import { useRef, useState } from 'react';
import {
  ChevronDown, ShieldCheck, LogOut, Mic, Type, PanelLeft, PanelRight, Camera, Trash2,
  Check, Stethoscope, Compass, GraduationCap, BookOpen, PenLine, RotateCcw,
} from 'lucide-react';
import PageShell from '@/components/PageShell';
import { cn } from '@/lib/cn';
import { useSignOut } from '@/hooks/useSignOut';
import {
  useAuthStore, CONSENT_PURPOSES, ACCOUNT_BLOCKING_PURPOSES, isConsentActive,
  type ConsentPurpose,
} from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';
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

const AVATAR_PX = 256;
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

/**
 * Read an image file and return a square, downscaled data URL.
 *
 * Centre-cropped to a square first, so a portrait photo does not arrive
 * stretched, then drawn at 256px. The store persists to localStorage and the
 * quota is ~5MB shared with everything else the app keeps there — putting the
 * original file in would evict the auth token along with it.
 */
function readSquareAvatar(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith('image/')) {
      reject(new Error('That file is not an image.'));
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      reject(new Error('That image is larger than 8MB. Try a smaller one.'));
      return;
    }

    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const side = Math.min(img.width, img.height);
      const canvas = document.createElement('canvas');
      canvas.width = AVATAR_PX;
      canvas.height = AVATAR_PX;
      const ctx = canvas.getContext('2d');
      if (!ctx) { reject(new Error('Could not process that image.')); return; }
      ctx.drawImage(
        img,
        (img.width - side) / 2, (img.height - side) / 2, side, side,
        0, 0, AVATAR_PX, AVATAR_PX,
      );
      resolve(canvas.toDataURL('image/jpeg', 0.85));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('That image could not be opened.'));
    };
    img.src = url;
  });
}

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

export default function ProfilePage() {
  const { signOut, signingOut, overlay } = useSignOut();

  const student = useAuthStore((s) => s.student);
  const guardian = useAuthStore((s) => s.guardian);
  const email = useAuthStore((s) => s.email);
  const tier = useAuthStore((s) => s.tier);
  const studentCode = useAuthStore((s) => s.studentCode);
  const accountStatus = useAuthStore((s) => s.accountStatus);
  const consents = useAuthStore((s) => s.consents);
  const setStudentProfile = useAuthStore((s) => s.setStudentProfile);
  const grantConsent = useAuthStore((s) => s.grantConsent);
  const withdrawConsent = useAuthStore((s) => s.withdrawConsent);

  const phasesDone = useNumeraStore((s) => s.phasesDone);
  const panelSide = useNumeraStore((s) => s.panelSide);
  const setPanelSide = useNumeraStore((s) => s.setPanelSide);
  const inputMode = useNumeraStore((s) => s.inputMode);
  const setInputMode = useNumeraStore((s) => s.setInputMode);

  const initials =
    (student.name || email || 'N')
      .split(/[\s@._]/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join('') || 'N';

  const done = PHASE_ORDER.filter((p) => phasesDone.includes(p)).length;
  const pct = Math.round((done / PHASE_ORDER.length) * 100);

  const activeConsents = CONSENT_PURPOSES.filter((p) => isConsentActive(consents, p.id)).length;
  const status = ACCOUNT_STATUS_COPY[accountStatus] ?? {
    label: accountStatus,
    dot: 'bg-muted-gray',
  };

  const toggleConsent = (id: ConsentPurpose) =>
    isConsentActive(consents, id) ? withdrawConsent(id) : grantConsent(id);

  const fileRef = useRef<HTMLInputElement>(null);
  const [avatarError, setAvatarError] = useState<string | null>(null);

  const pickAvatar = async (file: File | undefined) => {
    if (!file) return;
    setAvatarError(null);
    try {
      setStudentProfile({ avatar: await readSquareAvatar(file) });
    } catch (e) {
      // Surfaced on the card. A silent failure here reads as "upload is
      // broken" when the real cause is a HEIC file or a 40MB photo.
      setAvatarError(e instanceof Error ? e.message : 'Could not use that image.');
    }
  };


  /* How much of the profile the student has actually filled in. Honest: it
     counts fields that exist, so it drops to 0% on a fresh account rather than
     showing a flattering number nobody earned. */
  const fields = [
    student.name, student.avatar, student.gradeBand, student.ageBand,
    email, guardian.name, guardian.email, guardian.verified ? 'y' : '',
  ];
  const filled = fields.filter(Boolean).length;
  const setupPct = Math.round((filled / fields.length) * 100);

  return (
    <PageShell
      title={student.name ? `Welcome in, ${student.name.split(' ')[0]}` : 'Your profile'}
      subtitle="Your account, how you learn, and what you have agreed to."
      wide
    >
      {overlay}

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
            <Stat value={done} sub={`of ${PHASE_ORDER.length}`} label="Phases" />
            <Stat value={activeConsents} sub={`of ${CONSENT_PURPOSES.length}`} label="Permissions" />
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

            {/* A real <label for> rather than a button calling input.click().
                The button sat at the same z-index as the name plate below it,
                so the plate — later in the DOM — swallowed the clicks and
                "Add a photo" did nothing. A label needs no JS at all. */}
            <input
              ref={fileRef}
              id="avatar-input"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="sr-only"
              onChange={(e) => { void pickAvatar(e.target.files?.[0]); e.target.value = ''; }}
            />

            <label
              htmlFor="avatar-input"
              title={student.avatar ? 'Change photo' : 'Add a photo'}
              className={cn(
                'group z-30 cursor-pointer text-white',
                student.avatar
                  ? 'absolute top-3 right-3 w-9 h-9 rounded-full bg-black/45 hover:bg-black/70 backdrop-blur-sm flex items-center justify-center transition-colors'
                  : 'absolute inset-0 flex flex-col items-center justify-center gap-3',
              )}
            >
              {student.avatar ? (
                <Camera size={16} strokeWidth={1.9} />
              ) : (
                <>
                  <span
                    className="w-16 h-16 rounded-full flex items-center justify-center transition-colors"
                    style={{ background: 'rgba(0,0,0,0.10)', border: '1px solid rgba(0,0,0,0.18)', color: ON_GREEN }}
                  >
                    <Camera size={24} strokeWidth={1.6} />
                  </span>
                  <span className="text-[12.5px] font-semibold tracking-[0.3px]" style={{ color: ON_GREEN }}>
                    Add a photo
                  </span>
                </>
              )}
            </label>

            {student.avatar && (
              <button
                type="button"
                onClick={() => { setStudentProfile({ avatar: null }); setAvatarError(null); }}
                aria-label="Remove profile photo"
                className="absolute top-3 right-14 z-30 w-9 h-9 rounded-full bg-black/45 hover:bg-action-orange backdrop-blur-sm text-white flex items-center justify-center transition-colors"
              >
                <Trash2 size={15} strokeWidth={1.9} />
              </button>
            )}

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

            {avatarError && (
              <p role="alert" className="absolute bottom-20 left-4 right-4 z-20 text-[11px] text-white bg-action-orange rounded-lg px-2.5 py-1.5 text-center leading-snug">
                {avatarError}
              </p>
            )}
          </div>

          {/* Progress — the reference's bar chart. One bar per phase; a full
              bar is an unlocked phase. */}
          <Card className="xl:col-span-3 min-h-[330px]">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[16px] font-semibold text-ink">Progress</div>
                <div className="text-[11.5px] text-slate-blue mt-0.5">Through this topic</div>
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
              <div className="text-[15px] font-semibold">Learning flow</div>
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
            <Disclosure
              title="Guardian"
              meta={
                guardian.verified ? (
                  <span className="flex items-center gap-1.5 text-[11px] font-semibold text-success-sage">
                    <ShieldCheck size={13} strokeWidth={2} /> Verified
                  </span>
                ) : (
                  <span className="text-[11px] font-semibold text-action-orange">Unverified</span>
                )
              }
            >
              <Field label="Name" value={guardian.name || <Unknown>Not set</Unknown>} />
              <Field label="Relationship" value={guardian.relationship || <Unknown>Not set</Unknown>} />
              <Field label="Email" value={guardian.email || <Unknown>Not set</Unknown>} />
              <Field label="Phone" value={guardian.phone || <Unknown>Not set</Unknown>} />
            </Disclosure>

            <Disclosure title="Account">
              <Field label="Email" value={email || <Unknown>Not set</Unknown>} />
              <Field label="Student code" value={studentCode || <Unknown>Not issued yet</Unknown>} />
              <Field label="Plan" value={tier || <Unknown>Not set</Unknown>} />
              <Field label="Age band" value={student.ageBand || <Unknown>Not set</Unknown>} />
            </Disclosure>

            <Disclosure
              title="Privacy & permissions"
              meta={
                <span className="text-[11px] text-slate-blue tabular-nums">
                  {activeConsents}/{CONSENT_PURPOSES.length}
                </span>
              }
            >
              <p className="text-[12px] text-slate-blue leading-relaxed pt-3 pb-1">
                Turning off a <strong className="font-semibold text-ink">Required</strong> permission
                restricts the whole account until you turn it back on. The other
                two only disable their own feature.
              </p>
              <div className="mt-2 divide-y divide-muted-gray/60">
                {CONSENT_PURPOSES.map((p) => {
                  const on = isConsentActive(consents, p.id);
                  const blocking = ACCOUNT_BLOCKING_PURPOSES.includes(p.id);
                  return (
                    <div key={p.id} className="py-3 flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[13px] font-medium text-ink">{p.label}</span>
                          {blocking && (
                            <span className="rounded-full bg-reading-surface text-slate-blue px-2 py-0.5 text-[9.5px] font-semibold tracking-[0.4px] uppercase">
                              Required
                            </span>
                          )}
                        </div>
                        <p className="text-[11.5px] text-slate-blue mt-0.5 leading-snug">{p.detail}</p>
                      </div>
                      <button
                        onClick={() => toggleConsent(p.id)}
                        role="switch"
                        aria-checked={on}
                        aria-label={p.label}
                        className={cn(
                          'flex-shrink-0 w-11 h-6 rounded-full relative transition-colors',
                          !on && 'bg-muted-gray',
                        )}
                        style={on ? { background: GREEN } : undefined}
                      >
                        <span
                          className={cn(
                            'absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all',
                            on ? 'left-[22px]' : 'left-0.5',
                          )}
                        />
                      </button>
                    </div>
                  );
                })}
              </div>
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

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mt-6">
              <PrefGroup
                label="Tutor input"
                options={[
                  { id: 'voice', label: 'Voice', icon: Mic },
                  { id: 'text',  label: 'Text',  icon: Type },
                ]}
                value={inputMode}
                onPick={(v) => setInputMode(v as 'voice' | 'text')}
              />
              <PrefGroup
                label="Tutor panel side"
                options={[
                  { id: 'left',  label: 'Left',  icon: PanelLeft },
                  { id: 'right', label: 'Right', icon: PanelRight },
                ]}
                value={panelSide}
                onPick={(v) => setPanelSide(v as 'left' | 'right')}
              />
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

/** A pair of pill buttons bound to a store value. */
function PrefGroup({
  label, options, value, onPick,
}: {
  label: string;
  options: { id: string; label: string; icon: typeof Mic }[];
  value: string;
  onPick: (id: string) => void;
}) {
  return (
    <div>
      <div className="text-[11.5px] text-slate-blue mb-2">{label}</div>
      <div className="flex gap-2">
        {options.map(({ id, label: l, icon: Icon }) => {
          const on = value === id;
          return (
            <button
              key={id}
              onClick={() => onPick(id)}
              aria-pressed={on}
              className={cn(
                'flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-[13px] font-medium transition-colors',
                !on && 'bg-reading-surface text-slate-blue hover:text-ink',
              )}
              style={on ? { background: GREEN, color: ON_GREEN } : undefined}
            >
              <Icon size={15} strokeWidth={1.9} /> {l}
            </button>
          );
        })}
      </div>
    </div>
  );
}
