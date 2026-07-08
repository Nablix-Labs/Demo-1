import type { Metadata } from 'next';
import './globals.css';
import AppFrame from '@/components/AppFrame';
import FlowControls from '@/components/FlowControls';

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
      <body className="h-screen overflow-hidden bg-white font-sans text-ink">
        {/* App shell — the tool rail and media panel persist across every route.
            Full-bleed: fills the viewport edge-to-edge (no centred gutter). */}
        <div
          className="h-screen flex bg-white w-full"
          aria-label="Numera AI Math Tutor"
        >
          <AppFrame>{children}</AppFrame>
        </div>
        {/* Demo Director — drives the adaptive loop by hand (remove for prod) */}
        <FlowControls />
      </body>
    </html>
  );
}
