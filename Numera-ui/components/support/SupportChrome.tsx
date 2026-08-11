'use client';

/**
 * SupportChrome — mounts Nablix Assist everywhere except the pre-auth screens.
 *
 * The launcher used to render from the root layout, so a floating "Need help?"
 * pill sat over the login page — in-app chrome shown to someone who is not in
 * the app yet, and next to nothing it offers is usable before sign-in
 * (2026-07-28).
 */

import { usePathname } from 'next/navigation';
import { useNumeraStore } from '@/store/useNumeraStore';
import { isPhase3 } from '@/lib/phase3';
import NeedHelpButton from './NeedHelpButton';
import SupportPanel from './SupportPanel';
import RemoteAssistBanner from './RemoteAssistBanner';

/** Screens shown before a student is signed in. Kept in step with AppFrame. */
const PRE_AUTH_ROUTES = ['/login', '/onboard', '/consent', '/restricted', '/dev-screens'];

export default function SupportChrome() {
  const pathname = usePathname();
  // Phase 3 spec §3.2 lists "Need Help" among the affordances that must be
  // unavailable during an independent attempt. Assist is product support rather
  // than maths help, but it is a live channel to a person while the student is
  // being assessed alone, so it closes with the rest of them.
  const silentPhase3 = isPhase3(useNumeraStore((s) => s.currentPhase));
  const preAuth = PRE_AUTH_ROUTES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (preAuth || silentPhase3) return null;

  return (
    <>
      <NeedHelpButton />
      <SupportPanel />
      <RemoteAssistBanner />
    </>
  );
}
