'use client';

/**
 * SupportPanel — the Nablix Assist guided-help surface.
 *
 * An overlay next to the app (nothing unmounts, so form + canvas state is
 * preserved). The student describes the issue by voice (reusing useVoiceTurn)
 * or text; the assist backend (stubbed in lib/support/assistApi) replies with
 * an instruction, an element to spotlight, and/or an allow-listed safe action.
 * Actions with risk ≥ medium go through the ConsentModal, and "resolved" is
 * only reported after the action's verify() passes.
 */

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Send, Mic, MicOff, X, LifeBuoy } from 'lucide-react';
import { useSupportStore } from '@/store/useSupportStore';
import { useVoiceTurn } from '@/hooks/useVoiceTurn';
import { useMicLevel } from '@/store/useMicLevel';
import { getSupportContext } from '@/lib/support/supportContext';
import { requestSupportInstruction, reportActionResult } from '@/lib/support/assistApi';
import { highlightBySupportId, clearHighlight } from '@/lib/support/highlight';
import { getSafeAction, type SafeAction } from '@/lib/support/supportActions';
import { listInputDevices, type InputDevice } from '@/lib/support/diagnostics';
import { getPreferredMicId, setPreferredMicId } from '@/lib/support/micPreference';
import ConsentModal from './ConsentModal';
import EscalationPanel from './EscalationPanel';
import { cn } from '@/lib/cn';

const GREETING =
  "Hi, I'm Nablix Assist. Tell me what's going wrong — for example \"my mic isn't working\" or \"I can't submit my answer\".";

export default function SupportPanel() {
  const router = useRouter();
  const open = useSupportStore((s) => s.open);
  const messages = useSupportStore((s) => s.messages);
  const instruction = useSupportStore((s) => s.instruction);
  const pendingAction = useSupportStore((s) => s.pendingAction);
  const busy = useSupportStore((s) => s.busy);
  const textOnly = useSupportStore((s) => s.textOnly);
  const devicePickerOpen = useSupportStore((s) => s.devicePickerOpen);
  const setDevicePickerOpen = useSupportStore((s) => s.setDevicePickerOpen);
  const setEscalationOpen = useSupportStore((s) => s.setEscalationOpen);
  const closeSupport = useSupportStore((s) => s.closeSupport);
  const addMessage = useSupportStore((s) => s.addMessage);
  const setInstruction = useSupportStore((s) => s.setInstruction);
  const setPendingAction = useSupportStore((s) => s.setPendingAction);
  const setBusy = useSupportStore((s) => s.setBusy);
  const setTextOnly = useSupportStore((s) => s.setTextOnly);

  const [text, setText] = useState('');
  const [devices, setDevices] = useState<InputDevice[]>([]);
  const listRef = useRef<HTMLDivElement>(null);
  const lastIssueRef = useRef('');

  const caption = useMicLevel((s) => s.caption);

  const runAction = useCallback(
    async (action: SafeAction) => {
      setBusy(true);
      try {
        const ctx = { navigate: (path: string) => router.push(path) };
        await action.execute(ctx);
        const ok = await action.verify(ctx);
        const context = await getSupportContext();
        void reportActionResult({
          action_id: action.id,
          verification_status: ok ? 'verified' : 'failed',
          context,
        });
        const detail = action.describeResult?.();
        addMessage({
          role: 'assist',
          text: ok
            ? `Done — I've ${action.completedLabel}.${detail ? ` ${detail}` : ''} Did that fix it?`
            : `I tried to ${action.label} but couldn't confirm it worked.${detail ? ` ${detail}` : ''} Tap "Contact support" below and a human will take over.`,
        });
      } finally {
        setBusy(false);
      }
    },
    [router, addMessage, setBusy],
  );

  const submitIssue = useCallback(
    async (raw: string) => {
      const issue = raw.trim();
      if (!issue || busy) return;
      lastIssueRef.current = issue;
      addMessage({ role: 'user', text: issue });
      setBusy(true);
      try {
        const context = await getSupportContext();
        // If the problem IS the mic, voice input can't be the answer — switch
        // the student to text.
        if (/\bmic|microphone\b/i.test(issue) || context.mic_permission === 'denied') {
          setTextOnly(true);
        }
        const res = await requestSupportInstruction(issue, context);
        setInstruction(res);
        addMessage({ role: 'assist', text: res.instruction_text });
        if (res.highlight_support_id) {
          const found = highlightBySupportId(res.highlight_support_id, res.instruction_text);
          if (!found) {
            addMessage({
              role: 'assist',
              text: "That control isn't on this screen. Tell me what you can see and I'll point you from there.",
            });
          }
        }
        if (res.action_id) {
          const action = getSafeAction(res.action_id);
          if (!action) {
            // Allow-list refusal: never act on an id the registry doesn't know.
            addMessage({
              role: 'assist',
              text: 'I was asked to do something outside my allowed actions, so I stopped for safety.',
            });
          } else if (action.requiresConfirmation || action.riskLevel !== 'low') {
            setPendingAction({ actionId: action.id, label: action.label });
          } else {
            await runAction(action);
          }
        }
      } finally {
        setBusy(false);
      }
    },
    [busy, addMessage, setBusy, setTextOnly, setInstruction, setPendingAction, runAction],
  );

  // Voice input for describing the issue — same engine as the tutor loop.
  const submitIssueRef = useRef(submitIssue);
  useEffect(() => {
    submitIssueRef.current = submitIssue;
  }, [submitIssue]);
  const voice = useVoiceTurn({
    onTurnEnd: (transcript) => void submitIssueRef.current(transcript),
  });
  const { stop: stopVoice } = voice;

  // Greet on first open; stop listening + drop any spotlight when closed.
  useEffect(() => {
    if (open && useSupportStore.getState().messages.length === 0) {
      addMessage({ role: 'assist', text: GREETING });
    }
    if (!open) {
      stopVoice();
      clearHighlight();
    }
  }, [open, addMessage, stopVoice]);

  // Keep the newest message in view.
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, open]);

  // Load the microphone list when the SELECT_INPUT_DEVICE picker opens.
  useEffect(() => {
    if (devicePickerOpen) void listInputDevices().then(setDevices);
  }, [devicePickerOpen]);

  const pickDevice = (device: InputDevice) => {
    setDevicePickerOpen(false);
    // Until mic permission is granted the browser hides device ids, so there's
    // nothing to switch to yet.
    if (!device.device_id) {
      addMessage({
        role: 'assist',
        text: 'The browser hides microphone details until it has mic permission. Allow the microphone (or run the mic test) first, then ask me to switch again.',
      });
      return;
    }
    setPreferredMicId(device.device_id);
    addMessage({
      role: 'assist',
      text: `Switched to "${device.label}". It will be used the next time the mic starts — try speaking to the tutor.`,
    });
  };

  const close = () => {
    stopVoice();
    clearHighlight();
    closeSupport();
  };

  const sendText = (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText('');
    void submitIssue(value);
  };

  const confirmWorked = () => {
    addMessage({ role: 'user', text: 'That worked' });
    setInstruction(null);
    clearHighlight();
    addMessage({
      role: 'assist',
      text: 'Great! Anything else, or tap "Return" to pick up where you left off.',
    });
  };

  const rejectWorked = () => {
    addMessage({ role: 'user', text: "That didn't work" });
    setInstruction(null);
    clearHighlight();
    addMessage({
      role: 'assist',
      text: 'Sorry about that. Try describing what you see now — or tap "Contact support" and a human will take over.',
    });
  };

  const cantFindIt = () => {
    addMessage({ role: 'user', text: "I can't find it" });
    clearHighlight();
    addMessage({
      role: 'assist',
      text: "No problem — it may be on a different screen. Tell me what you can see right now and I'll point you from there.",
    });
  };

  const escalate = () => {
    setInstruction(null);
    setEscalationOpen(true);
  };

  const onConsentConfirm = () => {
    const pending = pendingAction;
    setPendingAction(null);
    const action = pending && getSafeAction(pending.actionId);
    if (action) void runAction(action);
  };

  const onConsentCancel = () => {
    setPendingAction(null);
    addMessage({ role: 'assist', text: "Okay, I won't do that. Anything else I can help with?" });
  };

  if (!open) return null;

  const chip =
    'rounded-full border border-muted-gray bg-white px-2.5 py-1 text-[10.5px] font-semibold text-slate-blue hover:text-ink hover:border-slate-blue transition-colors disabled:opacity-40';

  return (
    <>
      <aside
        className="lg-glass fixed top-2 bottom-14 right-2 z-[70] w-[300px] rounded-2xl flex flex-col overflow-hidden"
        aria-label="Nablix Assist support panel"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3.5 py-3 border-b border-muted-gray flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="w-7 h-7 rounded-lg bg-learning-blue text-white flex items-center justify-center flex-shrink-0">
              <LifeBuoy size={15} strokeWidth={1.8} />
            </span>
            <div className="leading-none">
              <div className="text-[13px] font-semibold text-ink">Nablix Assist</div>
              <div className="text-[8.5px] text-slate-blue tracking-[1.5px] uppercase mt-0.5">
                Support · lesson paused
              </div>
            </div>
          </div>
          <button
            onClick={close}
            aria-label="Exit support"
            className="w-6 h-6 rounded-md flex items-center justify-center text-slate-blue hover:bg-reading-surface hover:text-ink transition-colors"
          >
            <X size={15} strokeWidth={1.8} />
          </button>
        </div>

        {/* Support chat (separate from the lesson transcript) */}
        <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto px-3 py-3 flex flex-col gap-2">
          {messages.map((m) => (
            <div
              key={m.id}
              className={cn(
                'max-w-[85%] rounded-xl px-3 py-2 text-[11.5px] leading-snug',
                m.role === 'assist'
                  ? 'self-start bg-white border border-muted-gray text-ink'
                  : 'self-end bg-learning-blue text-white',
              )}
            >
              {m.text}
            </div>
          ))}
          {busy && (
            <div className="self-start text-[10.5px] text-slate-blue italic px-1" role="status">
              Nablix Assist is thinking…
            </div>
          )}
        </div>

        {/* Step controls for the current instruction */}
        {instruction && !busy && (
          <div className="px-3 pb-2 flex flex-wrap gap-1.5 flex-shrink-0">
            <button className={chip} onClick={confirmWorked}>✓ That worked</button>
            <button className={chip} onClick={rejectWorked}>✗ Didn&rsquo;t work</button>
            {instruction.highlight_support_id && (
              <>
                <button
                  className={chip}
                  onClick={() => highlightBySupportId(instruction.highlight_support_id!, instruction.instruction_text)}
                >
                  Show me again
                </button>
                <button className={chip} onClick={cantFindIt}>I can&rsquo;t find it</button>
              </>
            )}
            {instruction.escalate && (
              <button className={chip} onClick={escalate}>Contact support</button>
            )}
          </div>
        )}

        {/* Microphone picker (SELECT_INPUT_DEVICE) */}
        {devicePickerOpen && (
          <div className="mx-3 mb-2 rounded-md bg-white border border-muted-gray p-2 flex-shrink-0">
            <div className="text-[10px] font-semibold tracking-widest uppercase text-slate-blue mb-1.5 px-1">
              Pick a microphone
            </div>
            {devices.length === 0 ? (
              <p className="text-[11px] text-slate-blue px-1 pb-1">
                No microphones found. Check one is plugged in and allowed.
              </p>
            ) : (
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                {devices.map((d) => (
                  <button
                    key={d.device_id}
                    onClick={() => pickDevice(d)}
                    className={cn(
                      'text-left rounded-md px-2 py-1.5 text-[11.5px] transition-colors',
                      d.device_id === getPreferredMicId()
                        ? 'bg-learning-blue/10 text-learning-blue font-semibold'
                        : 'text-ink hover:bg-reading-surface',
                    )}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            )}
            <button
              onClick={() => setDevicePickerOpen(false)}
              className="mt-1.5 px-1 text-[10.5px] font-medium text-slate-blue hover:text-ink hover:underline"
            >
              Cancel
            </button>
          </div>
        )}

        {/* Voice status while listening */}
        {voice.active && (
          <div className="mx-3 mb-2 rounded-md bg-reading-surface border border-muted-gray px-2.5 py-1.5 text-center flex-shrink-0" aria-live="polite">
            <p className="text-[11px] text-ink leading-snug">
              {caption || <span className="text-slate-blue italic">Listening — describe the problem…</span>}
            </p>
          </div>
        )}
        {textOnly && (
          <p className="mx-3 mb-1.5 text-[10px] text-slate-blue italic flex-shrink-0">
            Mic looks unavailable — type below instead.
          </p>
        )}

        {/* Input row — text always available; voice unless the mic IS the issue */}
        <form
          onSubmit={sendText}
          className="flex items-center gap-2 px-3 pb-3 pt-2 border-t border-muted-gray flex-shrink-0"
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe the problem…"
            aria-label="Describe the problem"
            maxLength={500}
            className="flex-1 min-w-0 rounded-md border border-muted-gray bg-white px-2.5 py-1.5 text-[11.5px] text-ink placeholder:text-slate-blue focus:outline-none focus:border-learning-blue"
          />
          {!textOnly && voice.supported && (
            <button
              type="button"
              onClick={() => (voice.active ? voice.stop() : void voice.start())}
              aria-label={voice.active ? 'Stop voice input' : 'Describe the problem by voice'}
              className={cn(
                'flex-shrink-0 w-8 h-8 rounded-md flex items-center justify-center transition-colors',
                voice.active ? 'bg-action-orange text-white' : 'bg-reading-surface text-slate-blue hover:text-ink',
              )}
            >
              {voice.active ? <Mic size={14} strokeWidth={1.8} /> : <MicOff size={14} strokeWidth={1.8} />}
            </button>
          )}
          <button
            type="submit"
            aria-label="Send to Nablix Assist"
            disabled={!text.trim() || busy}
            className="flex-shrink-0 w-8 h-8 rounded-md bg-learning-blue text-white flex items-center justify-center transition-opacity disabled:opacity-40"
          >
            <Send size={14} strokeWidth={1.8} />
          </button>
        </form>

        {/* Footer — leave support (restores the exact pre-support state) */}
        <div className="flex items-center justify-between px-3 pb-3 flex-shrink-0">
          <button
            onClick={escalate}
            disabled={busy}
            className="text-[10.5px] font-medium text-slate-blue hover:text-ink hover:underline transition-colors disabled:opacity-40"
          >
            Contact support
          </button>
          <button
            onClick={close}
            className="rounded-full bg-focus-navy text-white px-3.5 py-1.5 text-[11px] font-semibold hover:brightness-110 transition"
          >
            Return to lesson
          </button>
        </div>
      </aside>

      {pendingAction && (
        <ConsentModal
          label={pendingAction.label}
          onConfirm={onConsentConfirm}
          onCancel={onConsentCancel}
        />
      )}

      <EscalationPanel issue={lastIssueRef.current} />
    </>
  );
}
