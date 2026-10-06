/** Profile contract: Student Model owns identity and persistence; Demo-1 proxies it. */
import axios from 'axios';
import { api } from '@/lib/api';
import { useAuthStore, type AccountStatus } from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';

export type AgeBand = '11–14 (KS3)' | '14–16 (KS4)';
export type GradeBand = 'Year 7' | 'Year 8' | 'Year 9' | 'Year 10' | 'Year 11';
export type PreferredMode = 'voice' | 'text' | 'balanced';

export interface ProfileGuardian {
  guardian_id: string;
  name: string | null;
  relationship: string | null;
  email: string | null;
  phone: string | null;
  verified: boolean | null;
}

export interface ProfileConsent {
  purpose: string;
  accepted_at: string | null;
  withdrawn_at: string | null;
}

export interface StudentProfile {
  student_id: string;
  student_code: string | null;
  email: string | null;
  tier: string | null;
  account_status: AccountStatus;
  display_name: string | null;
  age_band: AgeBand | null;
  grade_band: GradeBand | null;
  preferred_mode: PreferredMode | null;
  preferences: { input_mode: 'voice' | 'text' | null; panel_side: 'left' | 'right' | null };
  guardians: ProfileGuardian[];
  avatar_url: string | null;
  consents: ProfileConsent[] | null;
}

export interface StudentProfilePatch {
  display_name?: string;
  age_band?: AgeBand;
  grade_band?: GradeBand | null;
  preferred_mode?: PreferredMode;
  preferences?: { input_mode?: 'voice' | 'text'; panel_side?: 'left' | 'right' };
}

export async function fetchStudentProfile(accessToken: string): Promise<StudentProfile> {
  if (!accessToken.trim()) throw new Error('Please sign in to view your profile.');
  const response = await api.get<StudentProfile>('/students/me/profile', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  return response.data;
}

export async function patchStudentProfile(changes: StudentProfilePatch, accessToken: string): Promise<StudentProfile> {
  if (!accessToken.trim()) throw new Error('Please sign in to save your profile.');
  const response = await api.patch<StudentProfile>('/students/me/profile', changes, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  return response.data;
}

/** Mirror only a confirmed response for the same login that sent the request. */
export function applyConfirmedProfile(profile: StudentProfile, accessToken: string): void {
  const auth = useAuthStore.getState();
  if (auth.accessToken !== accessToken) throw new Error('Your login changed. Reload your profile before saving.');
  const name = profile.display_name?.trim() ?? '';
  useAuthStore.setState({
    studentCode: profile.student_code,
    studentName: name || null,
    email: profile.email ?? '',
    tier: profile.tier,
    accountStatus: profile.account_status,
    student: {
      ...auth.student,
      name,
      ageBand: profile.age_band ?? '',
      gradeBand: profile.grade_band ?? '',
      ...(profile.preferred_mode === null ? {} : { preferredMode: profile.preferred_mode }),
      avatar: profile.avatar_url,
    },
  });
  const lesson = useNumeraStore.getState();
  lesson.setStudentName(name);
  if (profile.preferences.input_mode !== null) lesson.setInputMode(profile.preferences.input_mode);
  if (profile.preferences.panel_side !== null) lesson.setPanelSide(profile.preferences.panel_side);
}

export function profileErrorMessage(error: unknown): string {
  if (axios.isAxiosError<{ message?: string }>(error)) {
    if (error.response?.status === 401) return 'Your login has expired. Please sign in again.';
    if (error.response?.status === 403) return 'You do not have permission to access this profile.';
    if (error.response?.status === 404) return 'Profile service is not available yet. Please try again later.';
    return error.response?.data?.message ?? 'Could not reach the profile service. Please try again.';
  }
  return error instanceof Error ? error.message : 'Could not load the profile. Please try again.';
}
