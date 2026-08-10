/**
 * The failure report has one job: make it impossible to argue about who broke.
 *
 * Written against the real shape of the 10 Aug outage — POST /interaction, 500,
 * INTERNAL_ERROR — because that is the case the report exists for.
 */

import { describe, it, expect } from 'vitest';
import { buildFailureReport, blameFor } from '@/lib/failureReport';

const axiosError = (over: Record<string, unknown> = {}) => ({
  config: {
    method: 'post',
    baseURL: '/api',
    url: '/interaction',
    data: JSON.stringify({ session_id: 'SESSION1', text_input: 'n+6' }),
  },
  response: {
    status: 500,
    data: { message: 'Internal server error', error_code: 'INTERNAL_ERROR', request_id: 'REQD6AA967B' },
  },
  ...over,
});

describe('buildFailureReport', () => {
  it('captures what we sent, parsed back from the request config', () => {
    // The caller never passes the payload — every catch site has the error and
    // none of them would reliably remember to thread the body through.
    const r = buildFailureReport(axiosError());
    expect(r.sentPayload).toEqual({ session_id: 'SESSION1', text_input: 'n+6' });
  });

  it('keeps the backend request_id, which is the grep key into its log', () => {
    expect(buildFailureReport(axiosError()).requestId).toBe('REQD6AA967B');
  });

  it('keeps the response body verbatim so our parsing cannot lose anything', () => {
    const r = buildFailureReport(axiosError());
    expect(r.responseBody).toMatchObject({ error_code: 'INTERNAL_ERROR' });
  });

  it('records the full URL and method', () => {
    const r = buildFailureReport(axiosError());
    expect(`${r.method} ${r.url}`).toBe('POST /api/interaction');
  });

  it('carries the lesson context it was given', () => {
    const r = buildFailureReport(axiosError(), { question_id: 'Q-T01-004' });
    expect(r.context).toEqual({ question_id: 'Q-T01-004' });
  });

  it('uses null, not 0, when there was no response at all', () => {
    // 0 would read as "the server answered 0". A request that never completed
    // and a server that answered are different failures with different owners.
    const r = buildFailureReport({ message: 'Network Error' });
    expect(r.status).toBeNull();
    expect(r.serverMessage).toBe('Network Error');
  });

  it('survives an error with no shape at all', () => {
    expect(() => buildFailureReport(undefined)).not.toThrow();
    expect(buildFailureReport({}).url).toContain('no request config');
  });

  it('leaves a non-JSON request body as it found it', () => {
    const r = buildFailureReport(axiosError({ config: { url: '/canvas/submit', data: 'not json' } }));
    expect(r.sentPayload).toBe('not json');
  });
});

describe('blameFor', () => {
  it('names the backend on a 5xx', () => {
    // The whole point. "Couldn't reach the tutor" on a 500 sent two people to
    // read frontend code while the fault sat in a service log (7 and 10 Aug).
    expect(blameFor(buildFailureReport(axiosError()))).toMatch(/^BACKEND/);
  });

  it('names the network only when nothing came back', () => {
    expect(blameFor(buildFailureReport({}))).toMatch(/^NETWORK/);
  });

  it('separates a refusal from a breakage', () => {
    const r = buildFailureReport(axiosError({ response: { status: 403, data: {} } }));
    expect(blameFor(r)).toMatch(/^AUTH/);
  });

  it('calls a 4xx a contract failure, not a server breakage', () => {
    const r = buildFailureReport(axiosError({ response: { status: 422, data: {} } }));
    expect(blameFor(r)).toMatch(/^CONTRACT/);
  });
});
