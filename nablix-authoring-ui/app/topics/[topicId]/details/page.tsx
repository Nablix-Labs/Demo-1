'use client';

import { FileText, Pencil, Info, Target, ArrowRight, ClipboardList, Tag, Users, CircleCheck, SlidersHorizontal } from 'lucide-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useWorkspace } from '@/lib/workspace-context';
import { StatusPill } from '@/components/nablix/StatusPill';
import { CardHeader } from '@/components/nablix/GlassCard';
import { formatDateTime } from '@/lib/utils';

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[128px_minmax(0,1fr)] items-start gap-3 py-1.5">
      <dt className="text-xs font-semibold text-slate-blue">{label}</dt>
      <dd className="min-w-0 break-words text-sm text-ink">{value}</dd>
    </div>
  );
}

const DEPENDENT_PROMPTS = [
  { label: 'Phase', Icon: ClipboardList },
  { label: 'Question Type', Icon: Info },
  { label: 'Difficulty', Icon: SlidersHorizontal },
  { label: 'Item Family', Icon: Tag },
  { label: 'Role', Icon: Users },
  { label: 'Canonical Answer', Icon: CircleCheck },
];

export default function TopicDetailsPage() {
  const ws = useWorkspace();
  const { topicId } = useParams<{ topicId: string }>();
  if (!ws) return null;
  const d = ws.details;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      {/* Section header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-2xs font-bold uppercase tracking-widest text-learning-blue">
            <FileText className="h-3.5 w-3.5" /> Topic
          </div>
          <div className="mt-1 flex items-center gap-2.5">
            <h1 className="font-display text-xl font-bold text-focus-navy">{d.topic_title}</h1>
            <StatusPill status={d.lifecycle} />
          </div>
        </div>
        <button className="btn btn-secondary">
          <Pencil className="h-4 w-4" /> Edit Topic
        </button>
      </div>

      {/* Basic details */}
      <section className="sheet">
        <CardHeader icon={<FileText className="h-4 w-4" />} title="Basic Details" />
        <dl className="px-5 py-3">
          <Field label="Topic ID" value={<span className="font-mono text-xs">{d.topic_id}</span>} />
          <Field label="Topic Code" value={d.topic_code} />
          <Field label="Title" value={d.topic_title} />
          <Field label="KS Stage" value={d.ks_stage} />
          <Field label="Subject" value={d.subject} />
          <Field label="Sequence No." value={d.sequence_no} />
          <Field label="Status" value={<StatusPill status={d.status} />} />
          <Field label="Version" value={`v${d.version}`} />
          <Field label="Created" value={formatDateTime(d.created_at)} />
          <Field label="Last Updated" value={formatDateTime(d.updated_at)} />
        </dl>
        <div className="border-t border-muted-gray/70 px-5 py-3">
          <Field label="Learning Goal" value={d.learning_goal} />
          <Field label="Core Message" value={d.core_message} />
        </div>
      </section>

      {/* Dependent fields prompt (spec §3.1 / §10) */}
      <section className="rounded-card border border-learning-blue/25 bg-learning-blue/8 p-4">
        <div className="flex items-start gap-2.5">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-learning-blue" />
          <div>
            <h3 className="text-sm font-bold text-focus-navy">
              Dependent Fields Prompt <span className="font-medium text-slate-blue">(when adding a question)</span>
            </h3>
            <p className="mt-0.5 text-xs text-slate-blue">
              These fields are prompted together in one guided flow based on the selected node and context — the author never
              hops between pages to complete required records.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {DEPENDENT_PROMPTS.map(({ label, Icon }) => (
                <span key={label} className="lg-chip flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-2xs font-semibold text-slate-blue">
                  <Icon className="h-3.5 w-3.5 text-learning-blue" /> {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Micro-skills in this topic */}
      <section className="sheet overflow-hidden">
        <CardHeader
          icon={<Target className="h-4 w-4" />}
          title="Micro-skills in this Topic"
          action={
            <Link href={`/topics/${topicId}/micro-skills`} className="flex items-center gap-1 text-xs font-semibold text-learning-blue hover:underline">
              View all <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-muted-gray/70 text-left text-2xs uppercase tracking-wide text-slate-blue">
                <th className="px-5 py-2 font-bold">ID</th>
                <th className="px-3 py-2 font-bold">Title</th>
                <th className="px-3 py-2 text-center font-bold">Diag.</th>
                <th className="px-3 py-2 text-center font-bold">Worked</th>
                <th className="px-3 py-2 text-center font-bold">Guided</th>
                <th className="px-3 py-2 text-center font-bold">Indep.</th>
                <th className="px-3 py-2 text-center font-bold">Hints</th>
                <th className="px-3 py-2 font-bold">Status</th>
              </tr>
            </thead>
            <tbody>
              {ws.micro_skills.map((m) => (
                <tr key={m.micro_skill_id} className="border-b border-muted-gray/50 last:border-0 hover:bg-reading-surface">
                  <td className="px-5 py-2.5 font-mono text-2xs text-slate-blue">{m.micro_skill_id}</td>
                  <td className="px-3 py-2.5 font-semibold text-focus-navy">{m.skill_name}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums">{m.diagnostic}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums">{m.worked}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums">{m.guided}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums">{m.independent}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums">{m.hints}</td>
                  <td className="px-3 py-2.5">
                    <StatusPill status={m.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
