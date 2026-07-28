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
import NeedHelpButton from './NeedHelpButton';
import SupportPanel from './SupportPanel';
import RemoteAssistBanner from './RemoteAssistBanner';

/** Screens shown before a student is signed in. Kept in step with AppFrame. */
const PRE_AUTH_ROUTES = ['/login', '/onboard', '/consent', '/restricted'];

export default function SupportChrome() {
  const pathname = usePathname();
  const preAuth = PRE_AUTH_ROUTES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (preAuth) return null;

  return (
    <>
      <NeedHelpButton />
      <SupportPanel />
      <RemoteAssistBanner />
    </>
  );
}
