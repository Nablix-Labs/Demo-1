'use client';

/**
 * YouTube-hosted orientation video.
 *
 * The blob-hosted MP4s are ~163 MB each and streamed straight from Azure, which
 * made the whole app feel slow while one was on screen (Manjusha, 2026-07-28).
 * YouTube serves an adaptive stream from a CDN, so the page stays responsive and
 * the student gets a quality matched to their connection.
 *
 * The IFrame API is loaded because the phase depends on knowing when playback
 * ENDS — a plain embed gives no such signal, and orientation cannot complete
 * without it (the backend rejects a completion that omits a served video).
 */

import { useEffect, useRef } from 'react';

/** Minimal shape of the bits of the YouTube IFrame API we use. */
interface YTPlayer {
  destroy: () => void;
}
interface YTNamespace {
  Player: new (el: HTMLElement, opts: Record<string, unknown>) => YTPlayer;
  PlayerState: { ENDED: number };
}
declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

const API_SRC = 'https://www.youtube.com/iframe_api';

/**
 * Resolve once the API is ready. The script must be injected only once per
 * page — a second copy re-defines the namespace and silently breaks any player
 * already constructed.
 */
let apiReady: Promise<void> | null = null;
function loadApi(): Promise<void> {
  if (apiReady) return apiReady;
  apiReady = new Promise<void>((resolve) => {
    if (window.YT?.Player) { resolve(); return; }
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { prev?.(); resolve(); };
    if (!document.querySelector(`script[src="${API_SRC}"]`)) {
      const tag = document.createElement('script');
      tag.src = API_SRC;
      document.head.appendChild(tag);
    }
  });
  return apiReady;
}

export default function YouTubeVideo({
  videoId, title, onEnded,
}: { videoId: string; title: string; onEnded: () => void }) {
  const hostRef = useRef<HTMLDivElement>(null);
  // Held in a ref so a re-render can't re-create the player mid-playback.
  const playerRef = useRef<YTPlayer | null>(null);
  // Read at fire time, so a changed handler doesn't require rebuilding the player.
  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;

  useEffect(() => {
    let cancelled = false;
    void loadApi().then(() => {
      if (cancelled || !hostRef.current || !window.YT) return;
      playerRef.current = new window.YT.Player(hostRef.current, {
        videoId,
        playerVars: {
          controls: 1,        // scrub, pause and volume — set explicitly, not assumed
          rel: 0,             // no unrelated videos at the end
          modestbranding: 1,
          playsinline: 1,
        },
        events: {
          onStateChange: (e: { data: number }) => {
            if (e.data === window.YT?.PlayerState.ENDED) onEndedRef.current();
          },
        },
      });
    });
    return () => {
      cancelled = true;
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [videoId]);

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-focus-navy bg-black">
      {/* The API replaces this node with the player iframe. */}
      <div ref={hostRef} className="w-full h-full" aria-label={title} />
    </div>
  );
}
