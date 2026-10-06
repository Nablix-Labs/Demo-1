'use client';

import { useEffect, useState } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import { applyConfirmedProfile, fetchStudentProfile, patchStudentProfile, profileErrorMessage } from '@/lib/studentProfile';
import type { StudentProfile, StudentProfilePatch } from '@/lib/studentProfile';

interface ProfileState {
  token: string | null;
  profile: StudentProfile | null;
  error: string | null;
}

interface ProfileResult {
  profile: StudentProfile | null;
  error: string | null;
  loading: boolean;
  saving: boolean;
  reload: () => void;
  save: (changes: StudentProfilePatch) => Promise<StudentProfile>;
}

/** Both screens load the same resource. Never render a previous login's response. */
export function useStudentProfile(): ProfileResult {
  const token = useAuthStore((state) => state.accessToken);
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<ProfileState>({ token: null, profile: null, error: null });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setState({ token, profile: null, error: null });
    if (!token) {
      setState({ token, profile: null, error: 'Please sign in to view your profile.' });
      setLoading(false);
      return;
    }
    void fetchStudentProfile(token).then((profile) => {
      if (!active || useAuthStore.getState().accessToken !== token) return;
      applyConfirmedProfile(profile, token);
      setState({ token, profile, error: null });
    }).catch((error: unknown) => {
      if (active && useAuthStore.getState().accessToken === token) {
        setState({ token, profile: null, error: profileErrorMessage(error) });
      }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, revision]);

  const save = async (changes: StudentProfilePatch): Promise<StudentProfile> => {
    if (!token || saving) throw new Error('Sign in and wait for any current save to finish.');
    setSaving(true);
    setState((previous) => ({ ...previous, error: null }));
    try {
      const profile = await patchStudentProfile(changes, token);
      applyConfirmedProfile(profile, token);
      setState({ token, profile, error: null });
      return profile;
    } catch (error: unknown) {
      if (useAuthStore.getState().accessToken === token) {
        setState((previous) => ({ ...previous, error: profileErrorMessage(error) }));
      }
      throw error;
    } finally {
      setSaving(false);
    }
  };

  return {
    profile: state.token === token ? state.profile : null,
    error: state.token === token ? state.error : null,
    loading: loading || state.token !== token,
    saving,
    reload: () => setRevision((previous) => previous + 1),
    save,
  };
}
