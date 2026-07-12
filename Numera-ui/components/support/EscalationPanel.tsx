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
import { X, Camera, MonitorUp, Send } from 'lucide-react';
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
  'Never: passwords, verification codes, or payment details',
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
      className="fixed inset-0 z-[85] flex items-center justify-center bg-ink/30"
      role="dialog"
      aria-modal="true"
      aria-label="Contact support"
    >
      <div
        className="w-[400px] max-w-[calc(100vw-32px)] bg-white rounded-xl border border-muted-gray p-5 max-h-[85vh] overflow-y-auto"
        style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.22)' }}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-[15px] font-semibold text-ink">Contact the support team</h2>
          <button
            onClick={close}
            aria-label="Close escalation form"
            className="w-6 h-6 rounded-md flex items-center justify-center text-slate-blue hover:bg-reading-surface hover:text-ink transition-colors"
          >
            <X size={15} strokeWidth={1.8} />
          </button>
        </div>

        <p className="text-[12px] text-slate-blue mt-1 leading-relaxed">
          A human will pick this up. Here&rsquo;s what gets shared:
        </p>
        <ul className="mt-2 flex flex-col gap-1">
          {SHARED_ITEMS.map((item) => (
            <li key={item} className="text-[11.5px] text-ink leading-snug flex gap-2">
              <span className="text-learning-blue flex-shrink-0">•</span>
              {item}
            </li>
          ))}
        </ul>

        <label className="block mt-4 text-[12px] font-semibold text-ink">
          Anything else they should know?
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional — e.g. when it started, what you already tried"
            rows={3}
            maxLength={500}
            className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3 py-2 text-[12.5px] text-ink placeholder:text-slate-blue focus:border-learning-blue focus:outline-none transition-colors resize-none"
          />
        </label>

        <label className="flex items-start gap-2.5 mt-3 cursor-pointer">
          <input
            type="checkbox"
            checked={includeScreenshot}
            onChange={(e) => setIncludeScreenshot(e.target.checked)}
            className="mt-0.5 accent-learning-blue"
          />
          <span className="text-[12px] text-ink leading-snug">
            <Camera size={12} className="inline mr-1 text-slate-blue" />
            Include a screenshot of my screen. Passwords, codes and personal fields are
            hidden automatically, and the image isn&rsquo;t stored on this device.
          </span>
        </label>

        <button
          onClick={() => void submit()}
          disabled={sending}
          className="btn btn-primary w-full mt-4 !py-2.5 text-[13px]"
        >
          {sending ? 'Sending…' : <>Send to support <Send size={14} /></>}
        </button>

        {!remoteAssistActive && (
          <button
            onClick={() => void shareScreen()}
            disabled={sending}
            className="btn btn-secondary w-full mt-2 !py-2.5 text-[13px]"
          >
            <MonitorUp size={14} /> Let support view my screen live
          </button>
        )}
      </div>
    </div>
  );
}
