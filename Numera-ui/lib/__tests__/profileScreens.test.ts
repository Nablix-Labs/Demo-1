/** Real loopback HTTP screen checks; deployed Student Model persistence remains unverified. */
import { createServer } from 'node:http';
import type { IncomingMessage, ServerResponse, Server } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { act, createElement } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import type { Root } from 'react-dom/client';
import { beforeAll, afterAll, beforeEach, afterEach, describe, it, expect, vi } from 'vitest';
import { api } from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';
import ProfilePage from '@/app/profile/page';
import PeoplePage from '@/app/people/page';
import { fetchStudentProfile } from '@/lib/studentProfile';
import type { StudentProfile, StudentProfilePatch, ProfileGuardian } from '@/lib/studentProfile';

vi.mock('@/components/PageShell', () => ({
  default: ({ children }: { children: ReactNode }) => createElement('main', null, children),
  Chip: ({ children }: { children: ReactNode }) => createElement('span', null, children),
}));
vi.mock('@/hooks/useSignOut', () => ({ useSignOut: () => ({ signOut: vi.fn(), signingOut: false, overlay: null }) }));

const initial: StudentProfile = {
  student_id: '1', student_code: 'ST001', email: 'student@example.test', tier: 'tier_3',
  account_status: 'active', display_name: 'Original name', age_band: '11–14 (KS3)',
  grade_band: 'Year 9', preferred_mode: 'balanced',
  preferences: { input_mode: 'text', panel_side: 'left' }, guardians: [], avatar_url: null, consents: null,
};
const guardian = (id: string, name: string, verified: boolean | null): ProfileGuardian => ({
  guardian_id: id, name, verified, relationship: 'Parent', email: null, phone: null,
});
let server: Server;
let saved: StudentProfile;
let failPatch: boolean;
let requestCount: number;
let delayRejection: boolean;
let releaseRejection: (() => void) | null;
let lastPatch: StudentProfilePatch | null;
let container: HTMLDivElement;
let root: Root;
const originalBase = api.defaults.baseURL;

function reply(response: ServerResponse, status: number, body: object): void {
  response.writeHead(status, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
  response.end(JSON.stringify(body));
}
async function handle(request: IncomingMessage, response: ServerResponse): Promise<void> {
  if (request.method === 'OPTIONS') {
    response.writeHead(204, { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'authorization, content-type', 'Access-Control-Allow-Methods': 'GET, PATCH' });
    response.end(); return;
  }
  requestCount += 1;
  if (request.url !== '/students/me/profile') { reply(response, 404, { message: 'Wrong URL' }); return; }
  const token = request.headers.authorization;
  if (token === 'Bearer first' && delayRejection) {
    await new Promise<void>((resolve) => { releaseRejection = resolve; });
    reply(response, 401, { message: 'Previous login rejected' }); return;
  }
  if (token !== 'Bearer first' && token !== 'Bearer second') { reply(response, 401, { message: 'Expired login' }); return; }
  if (request.method === 'PATCH') {
    if (failPatch) { reply(response, 503, { message: 'Could not save. Please retry.' }); return; }
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(Buffer.from(chunk));
    lastPatch = JSON.parse(Buffer.concat(chunks).toString()) as StudentProfilePatch;
    saved = { ...saved, ...lastPatch, preferences: { ...saved.preferences, ...lastPatch.preferences } };
  }
  reply(response, 200, token === 'Bearer second' ? { ...initial, student_id: '2', display_name: 'Second student' } : saved);
}
beforeAll(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  server = createServer((request, response) => { void handle(request, response); });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  api.defaults.baseURL = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
afterAll(async () => { api.defaults.baseURL = originalBase; server.close(); await once(server, 'close'); });
beforeEach(() => {
  saved = structuredClone(initial); failPatch = false; lastPatch = null; requestCount = 0; delayRejection = false; releaseRejection = null;
  useAuthStore.setState({ accessToken: 'first', studentCode: 'untrusted-browser-code', studentName: 'Local name' });
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(() => root.unmount()); container.remove(); });
async function renderProfile(): Promise<void> {
  await act(async () => { root.render(createElement(ProfilePage)); });
  await vi.waitFor(() => expect(container.querySelector<HTMLInputElement>('input')?.value).toBe(saved.display_name));
}
async function changeName(name: string): Promise<void> {
  const input = container.querySelector<HTMLInputElement>('input[name="display_name"]');
  if (!input) throw new Error('Display name input missing.');
  await act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, name);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
async function submit(): Promise<void> {
  const form = container.querySelector('form');
  if (!form) throw new Error('Profile form missing.');
  await act(() => { form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  await vi.waitFor(() => expect(container.textContent).not.toContain('Saving…'));
}
describe('profile and people', () => {
  it('saves changed fields, mirrors confirmed state, and reloads it after remount', async () => {
    await renderProfile(); await changeName('Chiru'); await submit();
    expect(lastPatch).toEqual({ display_name: 'Chiru' });
    expect(container.textContent).toContain('Profile saved.');
    expect(useAuthStore.getState().studentName).toBe('Chiru');
    expect(useNumeraStore.getState().studentName).toBe('Chiru');
    await act(() => root.unmount()); root = createRoot(container);
    useAuthStore.setState({ studentName: 'Stale browser name' }); await renderProfile();
    expect(container.querySelector<HTMLInputElement>('input')?.value).toBe('Chiru');
    expect(useAuthStore.getState().studentCode).toBe('ST001');
  });
  it('retains confirmed state on save failure and has no local avatar or consent controls', async () => {
    await renderProfile(); failPatch = true; await changeName('Unsaved name'); await submit();
    expect(useAuthStore.getState().studentName).toBe('Original name');
    expect(saved.display_name).toBe('Original name');
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Could not save');
    expect(container.textContent).not.toContain('Profile saved.');
    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(container.querySelector('[role="switch"]')).toBeNull();
    expect(container.textContent).toContain('Permissions are read-only');
    expect(container.textContent).not.toContain('Granted');
  });
  it.each([0, 1, 2])('renders %i real guardians with no invented people or presence', async (count) => {
    saved = { ...saved, guardians: [guardian('g1', 'First guardian', true), guardian('g2', 'Second guardian', null)].slice(0, count) };
    await act(() => root.render(createElement(PeoplePage)));
    await vi.waitFor(() => expect(container.textContent).not.toContain('Loading your guardians'));
    expect(container.textContent).toContain('Numera AI'); expect(container.textContent).not.toContain('Priya');
    expect(container.textContent).not.toContain('Online'); expect(container.textContent).not.toContain('Manage consent');
    if (count === 0) expect(container.textContent).toContain('No guardian linked');
    if (count >= 1) expect(container.textContent).toContain('First guardian');
    if (count === 2) { expect(container.textContent).toContain('Second guardian'); expect(container.textContent).toContain('Verification not set'); }
  });
  it('switches profiles when the authenticated account changes', async () => {
    await renderProfile(); await act(() => useAuthStore.setState({ accessToken: 'second' }));
    await vi.waitFor(() => expect(container.querySelector<HTMLInputElement>('input')?.value).toBe('Second student'));
    expect(container.textContent).not.toContain('Original name');
  });
  it('a delayed 401 from an old token cannot sign out the next account', async () => {
    delayRejection = true;
    const rejected = fetchStudentProfile('first').catch((error: unknown) => error);
    await vi.waitFor(() => expect(releaseRejection).not.toBeNull());
    useAuthStore.setState({ accessToken: 'second' });
    const release = releaseRejection as (() => void) | null;
    if (!release) throw new Error('Delayed request not ready.');
    release();
    expect(await rejected).toBeInstanceOf(Error);
    expect(useAuthStore.getState().accessToken).toBe('second');
  });
  it('a 401 for the current login signs it out', async () => {
    useAuthStore.setState({ accessToken: 'expired' });
    await expect(fetchStudentProfile('expired')).rejects.toThrow();
    expect(useAuthStore.getState().accessToken).toBeNull();
  });
  it('requires a real login before making requests', async () => {
    useAuthStore.setState({ accessToken: null }); await act(() => root.render(createElement(PeoplePage)));
    expect(container.textContent).toContain('Please sign in'); expect(requestCount).toBe(0);
  });
});
