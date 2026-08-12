import type { Metadata } from 'next';
import 'katex/dist/katex.min.css';
import './globals.css';
import AppFrame from '@/components/AppFrame';
import SupportChrome from '@/components/support/SupportChrome';
import { caveat } from '@/lib/tutorFont';
import DebugJsonPanel from '@/components/DebugJsonPanel';

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
        {/* Dev-only JSON viewer (temporary — Manjusha, 12 Aug 2026). Mounted at
            the root so every phase is covered by one line, and renders null
            unless NEXT_PUBLIC_DEBUG_JSON=true and a call has been captured.
            To remove: delete this line, components/DebugJsonPanel.tsx,
            lib/debugJson.ts and the recordDebugCall calls in lib/api.ts. */}
        {/* Compared inline so the flag is a literal at build time. Note the
            panel's CODE still ships — webpack keeps the client-component chunk
            either way — but it is unreachable, and nothing is captured either,
            because recordDebugCall returns early on the same flag. So no
            student payload is ever held or shown in a normal build; deleting
            the four places listed above is what removes it outright. */}
        {process.env.NEXT_PUBLIC_DEBUG_JSON === 'true' && <DebugJsonPanel />}
      </body>
    </html>
  );
}
