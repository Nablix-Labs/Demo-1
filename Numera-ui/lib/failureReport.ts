/**
 * What we capture when a tutor call fails.
 *
 * Every backend failure so far has been reported to us as a photograph of a
 * phone screen. That is one sentence of student-facing copy — the least
 * informative thing on the page — and it costs an evening to work backwards
 * from it to a service log. Twice now the conclusion drawn from a screenshot
 * was "the frontend made this up", because the sentence IS ours; it is only
 * ever printed when the backend told us it failed.
 *
 * So: when a call fails, write down everything needed to place the blame
 * without a second round trip, in one block someone can copy out of the
 * console and paste into the group chat.
 *
 * The request body comes off the axios error's own `config`, not from the
 * caller — every catch site already has the error and none of them would
 * reliably remember to thread the payload through.
 *
 * ── What is NOT captured ────────────────────────────────────────────────────
 * Never the auth header. It travels on every one of these requests and a
 * report is meant to be pasted into a chat window.
 */

export interface FailureReport {
  when: string;
  method: string;
  url: string;
  status: number | null;
  errorCode: string | null;
  /** The backend's own id for this request. Greps straight to its service log. */
  requestId: string | null;
  /** The backend's message. Developer-facing — never shown to a student. */
  serverMessage: string | null;
  /** What we sent, parsed back from the request config. */
  sentPayload: unknown;
  /** The response body verbatim, so nothing is lost to our own parsing. */
  responseBody: unknown;
  /** Where the lesson thought it was when this happened. */
  context: Record<string, unknown>;
}

interface Axiosish {
  config?: { url?: string; method?: string; baseURL?: string; data?: unknown };
  response?: {
    status?: number;
    data?: { message?: string; error_code?: string; request_id?: string } & Record<string, unknown>;
  };
  message?: string;
}

/** The request body as an object when it was JSON, else whatever it was. */
function parseSent(data: unknown): unknown {
  if (typeof data !== 'string') return data ?? null;
  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}

export function buildFailureReport(
  err: unknown,
  context: Record<string, unknown> = {},
  now: string = new Date().toISOString(),
): FailureReport {
  const e = (err ?? {}) as Axiosish;
  const res = e.response;
  const cfg = e.config;
  return {
    when: now,
    method: (cfg?.method ?? 'POST').toUpperCase(),
    url: `${cfg?.baseURL ?? ''}${cfg?.url ?? '(no request config)'}`,
    // Null rather than 0: "no response at all" and "the server answered 0" are
    // different failures, and 0 would read as the latter.
    status: typeof res?.status === 'number' ? res.status : null,
    errorCode: typeof res?.data?.error_code === 'string' ? res.data.error_code : null,
    requestId: typeof res?.data?.request_id === 'string' ? res.data.request_id : null,
    serverMessage:
      typeof res?.data?.message === 'string'
        ? res.data.message
        : typeof e.message === 'string'
          ? e.message
          : null,
    sentPayload: parseSent(cfg?.data),
    responseBody: res?.data ?? null,
    context,
  };
}

/**
 * Who broke, in one word, for the top of the log.
 *
 * The whole point of the block below. A 500 is not "couldn't reach the tutor",
 * and saying so sends the next person to read frontend code and check the wifi
 * while the fault sits in a service log nobody opened.
 */
export function blameFor(report: FailureReport): string {
  if (report.status === null) return 'NETWORK — the request never completed';
  if (report.status >= 500) return 'BACKEND — the request arrived and the server broke on it';
  if (report.status === 429) return 'BACKEND — rate limited';
  if (report.status === 401 || report.status === 403) return 'AUTH — the request was refused';
  if (report.status >= 400) return 'CONTRACT — the server rejected what we sent';
  return 'UNKNOWN';
}

/** Last few reports, so the console can be read after the fact. */
const recent: FailureReport[] = [];
const MAX_RECENT = 20;

export function recentFailures(): FailureReport[] {
  return [...recent];
}

/**
 * Log a failure and keep it.
 *
 * Collapsed by default: a student hitting a broken turn three times should not
 * bury everything else in the console, but one click has the whole thing.
 */
export function reportFailure(
  label: string,
  err: unknown,
  context: Record<string, unknown> = {},
): FailureReport {
  const report = buildFailureReport(err, context);

  recent.push(report);
  if (recent.length > MAX_RECENT) recent.shift();
  // Reachable from the console as `__numeraFailures` — a tester can be talked
  // through `copy(__numeraFailures)` over a call, which is the fastest route
  // from "it broke on my machine" to something a backend engineer can read.
  if (typeof window !== 'undefined') {
    (window as unknown as { __numeraFailures?: FailureReport[] }).__numeraFailures = recentFailures();
  }

  /* eslint-disable no-console */
  console.groupCollapsed(
    `%c✗ ${label} — ${blameFor(report)}`,
    'color:#b00020;font-weight:600',
  );
  console.log('status    ', report.status, report.errorCode ?? '');
  console.log('request_id', report.requestId ?? '(none — backend sent no id)');
  console.log('server    ', report.serverMessage ?? '(no message)');
  console.log('url       ', `${report.method} ${report.url}`);
  console.log('context   ', report.context);
  console.log('sent      ', report.sentPayload);
  console.log('received  ', report.responseBody);
  // One paste-able blob. Everything above is for reading; this is for sending.
  console.log('copy this →\n' + JSON.stringify(report, null, 2));
  console.groupEnd();
  /* eslint-enable no-console */

  return report;
}
