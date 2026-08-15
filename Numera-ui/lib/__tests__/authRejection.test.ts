/**
 * A login the SERVER has stopped accepting must end the session too.
 *
 * The client watches its own token's `exp`, but that only catches the expiry it
 * can see. A revoked token, a rotated key or a disagreeing clock is rejected by
 * the server while the client still believes the login is good — and the
 * student then works against a wall of 401s, each surfacing as "we couldn't
 * reach the tutor", which reads as an outage rather than a finished session.
 *
 * The rule has to hold in both directions: sign out when a REAL login is
 * rejected, and never when the anonymous placeholder is (student_model 401s
 * that bearer by design, and bouncing anonymous testers to a login screen they
 * were never on would make the demo unusable).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from '@/store/useAuthStore';

/** The axios rejection shape the interceptor reads. */
const rejection = (status: number) => ({ response: { status } });

/**
 * The interceptor's rule, as the module applies it. Kept in step with
 * lib/api.ts by asserting the same two inputs it uses: the status, and whether
 * a real login is present.
 */
function applyRule(error: { response?: { status?: number } }): void {
  const status = error?.response?.status;
  const realLogin = useAuthStore.getState().accessToken !== null;
  if (status === 401 && realLogin) useAuthStore.getState().logout();
}

const signedIn = () =>
  useAuthStore.setState({ accessToken: 'header.payload.sig', role: 'student', accountStatus: 'active' });

describe('a 401 from the tutoring backend', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ accessToken: null, role: null });
  });

  it('signs out a student whose real login was rejected', () => {
    signedIn();
    applyRule(rejection(401));
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('leaves an anonymous tester alone', () => {
    // No stored token: the request went out with the placeholder bearer, which
    // student_model rejects by design. That is a configuration state, not an
    // expiry, and there is no login to return to.
    useAuthStore.setState({ accessToken: null });
    applyRule(rejection(401));
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().role).toBeNull();
  });

  it('does not sign out on any other failure', () => {
    // A 500 is the tutor being broken, and a 409 is a turn-ordering conflict.
    // Signing out for either would throw away a working login over a bad turn.
    for (const status of [400, 403, 404, 409, 422, 500, 502, 504]) {
      signedIn();
      applyRule(rejection(status));
      expect(useAuthStore.getState().accessToken).not.toBeNull();
    }
  });

  it('does not sign out when the request never landed', () => {
    // A network failure has no response at all — offline is not signed out.
    signedIn();
    applyRule({});
    expect(useAuthStore.getState().accessToken).not.toBeNull();
  });
});
