import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  startRegistration, verifyRegistrationOtp, submitStudentProfile, submitGuardian,
  verifyGuardianOtp, acceptConsents, RegistrationError,
} from '@/lib/auth/registrationApi';

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe('registration on the mock path (no backend yet)', () => {
  it('asks for a code for email OTP and not for a password sign-up', async () => {
    const otp = await startRegistration({ method: 'email_otp', email: 'sam@example.com' });
    expect(otp.otp_required).toBe(true);
    expect(otp.otp_sent_to).toBe('s•••@example.com');
    const pw = await startRegistration({ method: 'password', email: 'sam@example.com', password: 'secret1' });
    expect(pw.otp_required).toBe(false);
  });

  it('accepts any 6 digits and rejects anything else', async () => {
    await expect(verifyRegistrationOtp('REG-1', '000000')).resolves.toEqual({ verified: true });
    await expect(verifyGuardianOtp('GRD-1', '12a')).rejects.toBeInstanceOf(RegistrationError);
  });

  it('issues no token, so the page activates the account locally', async () => {
    expect(await acceptConsents({
      registration_id: 'REG-1', guardian_id: 'GRD-1', accepted_purposes: [], disclosure_version: 'v1.0',
    })).toBeNull();
  });
});

describe('registration on the live path', () => {
  const live = (res: Response) => {
    vi.stubEnv('NEXT_PUBLIC_REGISTRATION_LIVE', 'true');
    const fetchMock = vi.fn().mockResolvedValue(res);
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
  };
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

  it('posts each step to its endpoint with the documented body', async () => {
    const f = live(json({ student_id: 'S1', student_code: 'ST101', account_status: 'consent_pending' }));
    await submitStudentProfile({
      registration_id: 'REG-1', display_name: 'Sam', age_band: '11–14 (KS3)', grade_band: 'Year 8', preferred_mode: 'voice',
    });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/nablix-auth/auth/register/profile');
    expect(JSON.parse(init.body)).toEqual({
      registration_id: 'REG-1', display_name: 'Sam', age_band: '11–14 (KS3)', grade_band: 'Year 8', preferred_mode: 'voice',
    });
  });

  it('sends a guardian with no phone as null, not an empty string', async () => {
    const f = live(json({ guardian_id: 'G1', otp_sent_to: 'p•••@x.com', expires_in_s: 600 }));
    await submitGuardian({ registration_id: 'REG-1', name: 'Pat', relationship: 'Parent', email: 'p@x.com', phone: null });
    expect(f.mock.calls[0][0]).toBe('/nablix-auth/consent/guardian');
    expect(JSON.parse(f.mock.calls[0][1].body).phone).toBeNull();
  });

  it("turns the server's error_code into student copy and keeps the field", async () => {
    live(json({ error_code: 'ACCOUNT_EXISTS', message: 'dup', field: 'email' }, 409));
    const err = await startRegistration({ method: 'email_otp', email: 'a@b.co' }).catch((e) => e);
    expect(err).toBeInstanceOf(RegistrationError);
    expect(err.code).toBe('ACCOUNT_EXISTS');
    expect(err.field).toBe('email');
    expect(err.message).toMatch(/already exists/);
  });

  it('reads a proxy HTML page as unreachable, not as a rejected sign-up', async () => {
    live(new Response('<html>502</html>', { status: 502 }));
    const err = await startRegistration({ method: 'email_otp', email: 'a@b.co' }).catch((e) => e);
    expect(err.message).toMatch(/Can't reach/);
  });
});
