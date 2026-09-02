'use client';

/**
 * Preview, Review & Publish — v3 page 15. Sections render in learner order, not
 * table order, and the action buttons come from workflow.available_actions —
 * they are not hard-coded here (guide §10.3).
 */
import { useEffect, useState } from 'react';
import { Send, Eye, ShieldCheck, CircleAlert, ArrowRight, Lock } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading } from '@/components/nablix/SectionHeader';
import { HealthBadge } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { PreviewPublishData } from '@/lib/api/v3-contracts';
import { cn } from '@/lib/utils';

/** Label for an action id the backend offers. Unknown ids render title-cased. */
function actionLabel(action: string) {
  return action
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/**
 * Which action ids this screen can actually carry out.
 *
 * Only two of the contract's actions have endpoints behind them
 * (`POST .../approve`, `POST .../return`, shipped 2 Sep 2026). VALIDATE,
 * PREVIEW and PUBLISH are still offered by `available_actions` and stay inert
 * here — a button that looks live and silently does nothing is worse than one
 * that is plainly not wired yet, so those render disabled with a reason.
 *
 * RETURN is matched under both names on purpose: the v3 sample calls it
 * `REQUEST_CHANGES` while the endpoint is `/return`, and the deployed
 * responses are untyped, so which id actually arrives is unconfirmed. Accepting
 * either costs nothing and avoids a dead button if the server says `RETURN`.
 */
const APPROVE_IDS = ['APPROVE'];
const RETURN_IDS = ['REQUEST_CHANGES', 'RETURN'];

function actionKind(action: string): 'approve' | 'return' | 'unwired' {
  if (APPROVE_IDS.includes(action)) return 'approve';
  if (RETURN_IDS.includes(action)) return 'return';
  return 'unwired';
}

export default function PublishPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [data, setData] = useState<PreviewPublishData | null>(null);
  /** The action awaiting a comment, or null when no panel is open. */
  const [commenting, setCommenting] = useState<'approve' | 'return' | null>(null);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    apiV3.getPreviewPublish(topicId).then(setData);
  }, [topicId]);

  const openPanel = (kind: 'approve' | 'return') => {
    setActionError(null);
    setDone(null);
    setComment('');
    setCommenting(kind);
  };

  const submitAction = async () => {
    if (!commenting) return;
    setSubmitting(true);
    setActionError(null);
    try {
      if (commenting === 'approve') await apiV3.approveTopic(topicId, comment);
      else await apiV3.returnTopic(topicId, comment);
      // Re-read rather than patching local state: `current_status`,
      // `available_actions` and `publish_allowed` are the backend's decision,
      // and guessing them here is how the two drift apart.
      setData(await apiV3.getPreviewPublish(topicId));
      setCommenting(null);
      setComment('');
      setDone(commenting === 'approve' ? 'Topic approved.' : 'Returned to the author.');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'The action could not be completed.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!data) return <SectionLoading />;

  const { workflow, learner_flow_sections } = data;
  const primary = workflow.available_actions.find((a) => /PUBLISH|APPROVE|SUBMIT/.test(a));
  // A return needs a reason; the server enforces it (`ReturnIn.minLength: 1`)
  // and so does this, so the approver learns before the request, not after.
  const canSubmit = commenting === 'approve' || comment.trim().length > 0;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Preview & Publish"
        icon={<Send className="h-3.5 w-3.5" />}
        title="Preview & Publish"
        description="Preview the topic in learner-flow order, then act. Available actions come from the topic's workflow state."
        action={
          <button className="btn btn-secondary">
            <Eye className="h-4 w-4" /> Open Preview
          </button>
        }
      />

      <section className="sheet overflow-hidden">
        <CardHeader icon={<Eye className="h-4 w-4" />} title="Learner Flow" />
        <div className="flex flex-wrap items-stretch gap-2 p-4">
          {learner_flow_sections.map((s, i) => (
            <div key={s.section} className="flex items-center gap-2">
              <div className="rounded-lg border border-muted-gray/70 bg-white px-3 py-2 text-center">
                <div className="font-display text-sm font-bold text-focus-navy">{s.section.replace(/_/g, ' ')}</div>
                <div className="mt-0.5 flex items-center justify-center gap-1.5 text-2xs text-slate-blue">
                  {s.count} items
                  <HealthBadge health={s.content_health} />
                </div>
              </div>
              {i < learner_flow_sections.length - 1 && <ArrowRight className="h-4 w-4 shrink-0 text-slate-blue/50" />}
            </div>
          ))}
        </div>
      </section>

      <section className="sheet">
        <CardHeader
          icon={<ShieldCheck className="h-4 w-4" />}
          title="Publish Readiness"
          action={
            <span className="rounded-pill bg-reading-surface px-2 py-0.5 text-2xs font-bold text-slate-blue ring-1 ring-inset ring-muted-gray/70">
              {workflow.current_status}
            </span>
          }
        />
        <div className="space-y-3 px-5 py-4">
          {workflow.publish_allowed ? (
            <div className="flex items-center gap-2 rounded-lg bg-success-sage/15 px-3 py-2.5 text-sm font-semibold text-[#5c6b58]">
              <ShieldCheck className="h-4 w-4" /> This topic can be published.
            </div>
          ) : (
            <div className="flex items-start gap-2 rounded-lg bg-danger/10 px-3 py-2.5 text-sm font-semibold text-danger">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              {workflow.publish_block_reason || 'Publishing is blocked.'}
            </div>
          )}

          <div className="flex flex-wrap gap-2 border-t border-muted-gray/50 pt-3">
            {workflow.available_actions.length === 0 ? (
              <span className="flex items-center gap-1.5 text-xs text-slate-blue">
                <Lock className="h-3.5 w-3.5" /> No actions available in this state.
              </span>
            ) : (
              workflow.available_actions.map((a) => {
                const kind = actionKind(a);
                return (
                  <button
                    key={a}
                    onClick={kind === 'unwired' ? undefined : () => openPanel(kind)}
                    // `publish_allowed` deliberately does NOT gate these. It
                    // used to disable whichever action was `primary`, which
                    // made Approve unpressable in IN_REVIEW — the one state
                    // where approving is the whole point, and the state that
                    // produces APPROVED and therefore publish_allowed. It gates
                    // PUBLISH, which has no endpoint and is disabled anyway.
                    disabled={kind === 'unwired' || submitting}
                    title={kind === 'unwired' ? 'No endpoint for this action yet.' : undefined}
                    className={cn('btn', a === primary ? 'btn-primary' : 'btn-secondary')}
                  >
                    {actionLabel(a)}
                  </button>
                );
              })
            )}
          </div>

          {/* The comment sits inline rather than in a modal: this page is the
              reviewer's one scrollable view of the topic's readiness, and the
              validation state they are writing about must stay on screen while
              they write. */}
          {commenting && (
            <div className="space-y-2 rounded-lg border border-muted-gray/70 bg-reading-surface/60 p-3">
              <label
                htmlFor="workflow-comment"
                className="block text-2xs font-bold uppercase tracking-wider text-slate-blue"
              >
                {commenting === 'return'
                  ? 'Why is this being returned?'
                  : 'Comment (optional)'}
              </label>
              <textarea
                id="workflow-comment"
                rows={3}
                autoFocus
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={
                  commenting === 'return'
                    ? 'Say what needs to change, so the author can act on it.'
                    : 'Anything worth recording with the approval.'
                }
                className="lg-field w-full resize-y text-sm"
              />
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => void submitAction()}
                  disabled={!canSubmit || submitting}
                  className="btn btn-primary"
                >
                  {submitting
                    ? 'Working…'
                    : commenting === 'approve'
                      ? 'Confirm approval'
                      : 'Return to author'}
                </button>
                <button
                  onClick={() => {
                    setCommenting(null);
                    setComment('');
                    setActionError(null);
                  }}
                  disabled={submitting}
                  className="btn btn-secondary"
                >
                  Cancel
                </button>
                {commenting === 'return' && !canSubmit && (
                  <span className="text-2xs text-slate-blue">A reason is required.</span>
                )}
              </div>
            </div>
          )}

          {actionError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg bg-danger/10 px-3 py-2.5 text-sm font-semibold text-danger"
            >
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              {actionError}
            </div>
          )}

          {done && (
            <div
              role="status"
              className="flex items-center gap-2 rounded-lg bg-success-sage/15 px-3 py-2.5 text-sm font-semibold text-[#5c6b58]"
            >
              <ShieldCheck className="h-4 w-4" /> {done}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
