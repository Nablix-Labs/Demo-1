'use client';

/**
 * AI Tutor tile — a live 3D avatar (Avatar3d) over a fail-soft orb.
 *
 * The 3D head is best-effort: it loads client-side and fades in over the orb
 * once ready; if WebGL/the model fails to load, the boundary drops it and the
 * orb stays. The avatar's mouth moves while Numera is speaking (voiceStatus).
 */

import { Component, useCallback, useState, type ReactNode } from 'react';
import dynamic from 'next/dynamic';

const Avatar3d = dynamic(() => import('./Avatar3d'), { ssr: false });

/** Any 3D load/render error unmounts the avatar so the orb beneath remains. */
class AvatarBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

const RobotIcon = ({ size }: { size: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="5" y="8" width="14" height="11" rx="2" />
    <line x1="12" y1="5" x2="12" y2="8" />
    <circle cx="12" cy="4" r="1" />
    <circle cx="9.5" cy="13" r="1" />
    <circle cx="14.5" cy="13" r="1" />
    <line x1="9" y1="16.5" x2="15" y2="16.5" />
  </svg>
);

export default function TutorTile() {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const showOrb = !ready || failed;
  const handleReady = useCallback(() => setReady(true), []);
  const handleError = useCallback(() => setFailed(true), []);

  return (
    <div
      className="relative border border-muted-gray rounded-md overflow-hidden bg-reading-surface"
      style={{ aspectRatio: '4/3' }}
      aria-label="AI tutor"
    >
      {/* Orb — shown while the 3D avatar loads, or as fallback if it fails */}
      <div
        className={
          'absolute inset-0 flex items-center justify-center transition-opacity duration-500 ' +
          (showOrb ? 'opacity-100' : 'opacity-0')
        }
      >
        <div className="relative w-20 h-20 flex items-center justify-center">
          <div className="absolute inset-0 rounded-full border border-dashed border-ai-cyan animate-spin-slow" />
          <div className="absolute inset-[7px] rounded-full border border-ai-cyan animate-pulse-ring" />
          <div className="w-[52px] h-[52px] rounded-full bg-white border border-muted-gray flex items-center justify-center text-focus-navy">
            <RobotIcon size={24} />
          </div>
        </div>
      </div>

      {/* Live 3D avatar */}
      {!failed && (
        <div className={'absolute inset-0 transition-opacity duration-500 ' + (ready ? 'opacity-100' : 'opacity-0')}>
          <AvatarBoundary onError={handleError}>
            <Avatar3d onReady={handleReady} />
          </AvatarBoundary>
        </div>
      )}

      {/* Name tag */}
      <div className="absolute left-2 bottom-2 z-10 bg-focus-navy/85 text-white text-[9.5px] px-2 py-0.5 rounded flex items-center gap-1">
        <RobotIcon size={12} />
        Numera
      </div>
    </div>
  );
}
