/**
 * Official SSO provider marks, inline so sign-in buttons stay crisp at any size.
 * Standard use for authentication buttons (Google/Microsoft/Apple brand guidelines).
 * "School ID" has no single brand, so it uses a Numera-navy graduation mark.
 */
import type { JSX } from 'react';
import type { SsoProvider } from '@/store/useAuthStore';

export function GoogleLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z" />
      <path fill="#FF3D00" d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z" />
      <path fill="#4CAF50" d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.211 35.091 26.715 36 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z" />
      <path fill="#1976D2" d="M43.611 20.083H42V20H24v8h11.303c-.792 2.237-2.231 4.166-4.087 5.571l6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z" />
    </svg>
  );
}

export function MicrosoftLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#F25022" d="M1 1h10v10H1z" />
      <path fill="#7FBA00" d="M13 1h10v10H13z" />
      <path fill="#00A4EF" d="M1 13h10v10H1z" />
      <path fill="#FFB900" d="M13 13h10v10H13z" />
    </svg>
  );
}

export function AppleLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="#000" aria-hidden="true">
      <path d="M17.05 12.04c-.03-3.02 2.47-4.47 2.58-4.54-1.41-2.06-3.6-2.34-4.38-2.37-1.86-.19-3.63 1.1-4.58 1.1-.94 0-2.4-1.07-3.95-1.04-2.03.03-3.9 1.18-4.94 3-2.11 3.66-.54 9.08 1.51 12.05 1 1.45 2.19 3.08 3.75 3.02 1.51-.06 2.08-.97 3.9-.97 1.81 0 2.33.97 3.92.94 1.62-.03 2.64-1.48 3.63-2.94 1.14-1.68 1.61-3.31 1.64-3.39-.04-.02-3.15-1.21-3.18-4.8zM14.13 4.28c.83-1 1.39-2.4 1.24-3.78-1.2.05-2.65.8-3.51 1.8-.77.88-1.44 2.28-1.26 3.63 1.34.1 2.7-.68 3.53-1.65z" />
    </svg>
  );
}

export function SchoolLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#1B2A4A" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 4 22 9 12 14 2 9z" />
      <path d="M6 11v5c0 1.1 2.7 2.5 6 2.5s6-1.4 6-2.5v-5" />
      <path d="M22 9v5" />
    </svg>
  );
}

export const SSO_LOGO: Record<SsoProvider, (p: { size?: number }) => JSX.Element> = {
  google: GoogleLogo,
  microsoft: MicrosoftLogo,
  apple: AppleLogo,
  school: SchoolLogo,
};
