'use client';

/**
 * EscalationPanel — hands the problem to a human.
 *
 * Shows exactly what will be shared before anything is sent; the screenshot is
 * opt-in (checkbox = consent), captured with sensitive fields masked, uploaded
 * and never stored locally. Live screen share is offered separately and puts
 * up the persistent RemoteAssistBanner. The panel is an overlay — the lesson,
 * forms and canvas underneath are untouched.
 */

import { useState } from 'react';
import { X, Camera, MonitorUp, Send, Headphones } from 'lucide-react';
import { useSupportStore } from '@/store/useSupportStore';
import { getSupportContext } from '@/lib/support/supportContext';
import { collectDiagnostics } from '@/lib/support/diagnostics';
import { escalateToSupport, uploadSupportScreenshot } from '@/lib/support/assistApi';
import { captureMaskedScreenshot } from '@/lib/support/screenshot';
import { startScreenShare } from '@/lib/support/remoteAssist';

const SHARED_ITEMS = [
  'Your issue description and this support chat',
  'Which screen and step you are on',
  'Device diagnostics: browser, connection, mic permission and status',
];

interface EscalationPanelProps {
  /** The issue text the escalation is about (last thing the student reported). */
  issue: string;
}

export default function EscalationPanel({ issue }: EscalationPanelProps) {
  const escalationOpen = useSupportStore((s) => s.escalationOpen);
  const setEscalationOpen = useSupportStore((s) => s.setEscalationOpen);
  const remoteAssistActive = useSupportStore((s) => s.remoteAssistActive);
  const addMessage = useSupportStore((s) => s.addMessage);

  const [note, setNote] = useState('');
  const [includeScreenshot, setIncludeScreenshot] = useState(false);
  const [sending, setSending] = useState(false);

  if (!escalationOpen) return null;

  const close = () => setEscalationOpen(false);

  const submit = async () => {
    if (sending) return;
    setSending(true);
    try {
      const [context, diagnostics] = await Promise.all([getSupportContext(), collectDiagnostics()]);

      let screenshot_reference: string | undefined;
      if (includeScreenshot) {
        // Consented above. Captured masked, uploaded, and dropped — not stored.
        const dataUrl = await captureMaskedScreenshot();
        screenshot_reference = (await uploadSupportScreenshot(dataUrl)).screenshot_reference;
      }

      const { reference_id } = await escalateToSupport({
        issue,
        note: note.trim(),
        context,
        diagnostics,
        screenshot_reference,
      });

      addMessage({
        role: 'assist',
        text: `I've passed this to the Nablix support team${screenshot_reference ? ' with your screenshot' : ''}. Your reference is ${reference_id} — keep it handy.`,
      });
      setEscalationOpen(false);
      setNote('');
      setIncludeScreenshot(false);
    } finally {
      setSending(false);
    }
  };

  const shareScreen = async () => {
    const started = await startScreenShare();
    addMessage({
      role: 'assist',
      text: started
        ? 'Screen sharing is on — support can now see your screen. The banner at the top has a Stop button whenever you want to end it.'
        : 'No problem — screen sharing stayed off.',
    });
    if (started) setEscalationOpen(false);
  };

  return (
    <div
      className="lg-scrim lg-anim-fade fixed inset-0 z-[85] flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="Contact support"
    >
      <div className="lg-sheet lg-anim-pop w-[410px] max-w-[calc(100vw-32px)] rounded-[26px] p-5 max-h-[85vh] overflow-y-auto lg-scroll">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="lg-lens w-10 h-10 rounded-full flex items-center justify-center text-white flex-shrink-0">
              <Headphones size={18} strokeWidth={1.9} aria-hidden="true" />
            </span>
            <h2 className="text-[15px] font-semibold text-ink tracking-[0.1px]">Contact the support team</h2>
          </div>
          <button
            onClick={close}
            aria-label="Close escalation form"
            className="lg-chip w-7 h-7 rounded-full flex items-center justify-center text-slate-blue hover:text-ink
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-learning-blue/50"
          >
            <X size={14} strokeWidth={2} />
          </button>
        </div>

        <p className="text-[12px] text-slate-blue mt-3 leading-relaxed">
          A human will pick this up. Here&rsquo;s what gets shared:
        </p>
        <ul className="lg-bubble mt-2 rounded-2xl px-3.5 py-2.5 flex flex-col divide-y divide-white/50">
          {SHARED_ITEMS.map((item) => (
            <li key={item} className="text-[11.5px] text-ink leading-snug flex gap-2 py-1.5 first:pt-0 last:pb-0">
              <span className="text-learning-blue flex-shrink-0" aria-hidden="true">•</span>
              {item}
            </li>
          ))}
          <li className="text-[11.5px] leading-snug flex gap-2 py-1.5 last:pb-0 font-medium text-ink">
            <span className="text-learning-blue flex-shrink-0" aria-hidden="true">•</span>
            Never: passwords, verification codes, or payment details
          </li>
        </ul>

        <label className="block mt-4 text-[12px] font-semibold text-ink">
          Anything else they should know?
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional — e.g. when it started, what you already tried"
            rows={3}
            maxLength={500}
            className="lg-field mt-1.5 w-full rounded-2xl px-3.5 py-2.5 text-[12.5px] text-ink placeholder:text-slate-blue/80 resize-none"
          />
        </label>

        <label className="lg-bubble flex items-start gap-2.5 mt-3 rounded-2xl px-3.5 py-2.5 cursor-pointer transition-colors hover:bg-white/80">
          <input
            type="checkbox"
            checked={includeScreenshot}
            onChange={(e) => setIncludeScreenshot(e.target.checked)}
            className="mt-0.5 accent-learning-blue"
          />
          <span className="text-[12px] text-ink leading-snug">
            <Camera size={12} className="inline mr-1 text-slate-blue" aria-hidden="true" />
            Include a screenshot of my screen. Passwords, codes and personal fields are
            hidden automatically, and the image isn&rsquo;t stored on this device.
          </span>
        </label>

        <button
          onClick={() => void submit()}
          disabled={sending}
          className="btn btn-primary w-full mt-4 !py-2.5 !rounded-full text-[13px]"
        >
          {sending ? 'Sending…' : <>Send to support <Send size={14} /></>}
        </button>

        {!remoteAssistActive && (
          <button
            onClick={() => void shareScreen()}
            disabled={sending}
            className="lg-chip w-full mt-2 rounded-full py-2.5 text-[13px] font-semibold text-ink/85 hover:text-ink
                       flex items-center justify-center gap-2 disabled:opacity-40
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-learning-blue/50"
          >
            <MonitorUp size={14} aria-hidden="true" /> Let support view my screen live
          </button>
        )}
      </div>
    </div>
  );
}
