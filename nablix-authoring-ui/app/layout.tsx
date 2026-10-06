import type { Metadata } from 'next';
import { Public_Sans, IBM_Plex_Mono } from 'next/font/google';
import './globals.css';
import { AuthGate } from '@/components/nablix/AuthGate';

// Public Sans — clean, neutral, highly legible — used across body + headings.
// IBM Plex Mono for IDs & codes.
const sans = Public_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800', '900'],
  variable: '--font-body',
  display: 'swap',
});
const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Nablix · Content Authoring Portal',
  description: 'Internal authoring portal for Nablix curriculum content.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <div className="lg-root">
          <div className="lg-ambient" />
          <AuthGate>{children}</AuthGate>
        </div>
      </body>
    </html>
  );
}
