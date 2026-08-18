'use client';

/**
 * Developer-only JSON viewer (spec §4, Manav).
 *
 * Renders nothing at all unless NEXT_PUBLIC_DEBUG_JSON=true AND a call has
 * actually been captured, so a production build has no control to find and an
 * untouched session has no empty drawer sitting on screen.
 *
 * To remove the feature entirely: delete this file and lib/debugJson.ts, then
 * drop the <DebugJsonPanel /> mount and the recordDebugCall lines in lib/api.ts.
 */

import { useState, useSyncExternalStore } from 'react';
import { ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';
import {
  debugJsonEnabled,
  subscribeDebugCapture,
  getDebugCapture,
  getDebugCaptureServer,
  formatJson,
} from '@/lib/debugJson';

type TabKey = 'sm_request' | 'sm_response' | 'request' | 'response';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'sm_request', label: 'SM Request' },
  { key: 'sm_response', label: 'SM Response' },
  { key: 'request', label: 'Tutor Request' },
  { key: 'response', label: 'Tutor Response' },
];

export default function DebugJsonPanel() {
  const capture = useSyncExternalStore(
    subscribeDebugCapture,
    getDebugCapture,
    getDebugCaptureServer,
  );
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<TabKey>('sm_request');
  const [copied, setCopied] = useState(false);

  // §4.2: hide the control entirely when there is no debug payload or debug
  // mode is off. Hooks run first so the order stays stable across renders.
  if (!debugJsonEnabled() || !capture) return null;

  const value =
    tab === 'sm_request' ? capture.studentModelRequest
    : tab === 'sm_response' ? capture.studentModelResponse
    : tab === 'request' ? capture.request
    : capture.response;
  const text = formatJson(value);

  const copy = () => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center">
      <div className="pointer-events-auto w-full max-w-5xl overflow-hidden rounded-t-xl border border-b-0 border-slate-700 bg-slate-900 text-slate-100 shadow-2xl">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-2 text-[12px] font-semibold hover:bg-slate-800"
        >
          <span className="flex items-center gap-2">
            <span className="rounded bg-amber-400 px-1.5 py-0.5 text-[10px] font-bold text-slate-900">
              DEV
            </span>
            View Debug JSON
            <span className="font-normal text-slate-400">
              {capture.endpoint} · {capture.at}
            </span>
          </span>
          {open ? <ChevronDown size={15} /> : <ChevronUp size={15} />}
        </button>

        {open && (
          <div className="border-t border-slate-700">
            <div className="flex items-center gap-1 px-3 py-2">
              {TABS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={
                    'rounded px-2.5 py-1 text-[11.5px] font-semibold transition-colors '
                    + (tab === key
                      ? 'bg-slate-100 text-slate-900'
                      : 'text-slate-300 hover:bg-slate-800')
                  }
                >
                  {label}
                </button>
              ))}
              <button
                onClick={copy}
                className="ml-auto flex items-center gap-1.5 rounded px-2.5 py-1 text-[11.5px] font-semibold text-slate-300 hover:bg-slate-800"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                {copied ? 'Copied' : 'Copy JSON'}
              </button>
            </div>
            <pre className="max-h-[45vh] overflow-auto px-4 pb-4 text-[11.5px] leading-relaxed text-slate-100">
              {text}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
