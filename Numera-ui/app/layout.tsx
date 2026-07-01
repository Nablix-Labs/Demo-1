import type { Metadata } from 'next';
import './globals.css';
import AppFrame from '@/components/AppFrame';
import FlowControls from '@/components/FlowControls';
import { SpeedInsights } from '@vercel/speed-insights/next';

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
      <body className="h-screen overflow-hidden bg-[#e2e2e2] font-sans">
        {/* App shell — the tool rail and media panel persist across every route */}
        <div
          className="h-screen flex bg-white max-w-[1500px] mx-auto border-x border-[#c8c8c8]"
          aria-label="Numera AI Math Tutor"
        >
          <AppFrame>{children}</AppFrame>
        </div>
        {/* Demo Director — drives the adaptive loop by hand (remove for prod) */}
        <FlowControls />
        <SpeedInsights />
      </body>
    </html>
  );
}
