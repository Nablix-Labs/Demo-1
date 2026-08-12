import type { Metadata } from 'next';
import 'katex/dist/katex.min.css';
import './globals.css';
import AppFrame from '@/components/AppFrame';
import SupportChrome from '@/components/support/SupportChrome';
import { caveat } from '@/lib/tutorFont';

export const metadata: Metadata = {
  title: 'Numera — AI Math Tutor',
  description: 'AI-powered maths tutoring for KS3–KS4 students by Nablix',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${caveat.variable} h-screen overflow-hidden lg-root font-sans text-ink`}>
        {/* Liquid Glass — vivid ambient backdrop the chrome lenses over. */}
        <div className="lg-ambient" aria-hidden="true" />
        {/* App shell — the tool rail and media panel persist across every route.
            Full-bleed: fills the viewport edge-to-edge (no centred gutter).
            Sits above the ambient layer. */}
        <div
          className="relative z-10 h-screen flex w-full"
          aria-label="Numera AI Math Tutor"
        >
          <AppFrame>{children}</AppFrame>
        </div>
        {/* Nablix Assist — in-app support. Mounted inside AppFrame so it can be
            withheld from the pre-auth screens: a "Need help?" launcher floating
            over the login page is in-app chrome shown to someone who is not in
            the app yet. */}
        <SupportChrome />
      </body>
    </html>
  );
}
