/**
 * One quiet resend for a tutor call that failed for a reason worth retrying.
 *
 * Sanya, 10 Oct: "I am getting errors due to frontend also because it doesn't
 * have any retry mechanism." The flaky guided 503 (master plan B1: a wrong
 * answer sometimes errors and works on retry) reached the student every time,
 * because every submit path showed the error on the first failure.
 *
 * Safe because every submission carries a turn_id and the backend dedupes on
 * turn_id + content: a resend of the SAME payload can never record a turn twice
 * (a finished first attempt is replayed, not re-graded).
 */
import axios from 'axios';

/**
 * Worth resending straight away, with no refresh in between:
 *  - the server errored (5xx), e.g. the classifier's ADAPTER_UNAVAILABLE;
 *  - the request never reached it (no response, and not a timeout — a timed-out
 *    turn may still be running, and a second 90s wait helps nobody);
 *  - a Teach-Back tutor reply failed the backend's checks (nothing recorded).
 * Never a 409 (session state matters: refresh first) or another 4xx (the
 * request itself is wrong, and will be again).
 */
export function isTransientFailure(err: unknown): boolean {
  if (!axios.isAxiosError(err)) return false;
  const status = err.response?.status;
  if (status === undefined) return err.code !== 'ECONNABORTED' && err.code !== 'ETIMEDOUT';
  const code = (err.response?.data as { error_code?: string } | undefined)?.error_code;
  return code === 'INVALID_TEACH_BACK_REPLY' || status >= 500;
}

/** Send; on a transient failure wait briefly and send the same request once more. */
export async function sendWithOneResend<T>(send: () => Promise<T>, pauseMs = 1200): Promise<T> {
  try {
    return await send();
  } catch (err) {
    if (!isTransientFailure(err)) throw err;
    console.warn('[tutor] transient failure, resending the same turn once', err);
    await new Promise((r) => setTimeout(r, pauseMs));
    return send();
  }
}
