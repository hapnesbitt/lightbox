'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import type { SlideshowItem } from '@/lib/types';

// Cast SDK custom element — registered by the SDK script at runtime
declare global {
  interface Window {
    __onGCastApiAvailable?: (isAvailable: boolean) => void;
  }
}
declare module 'react' {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      'google-cast-launcher': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
    }
  }
}

interface SlideshowPlayerProps {
  items: SlideshowItem[];
  batchName: string;
  startIndex?: number;
}

export function SlideshowPlayer({ items, batchName, startIndex = 0 }: SlideshowPlayerProps) {
  const [index, setIndex] = useState(Math.min(startIndex, items.length - 1));
  const [fullscreen, setFullscreen] = useState(false);
  const [playing, setPlaying] = useState(true);
  const [barActive, setBarActive] = useState(false);
  const [castAvailable, setCastAvailable] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const current = items[index];
  const total = items.length;

  // Auto-advance (used by timer and onEnded — does not pause playback)
  const advance = useCallback(() => setIndex((i) => (i + 1) % total), [total]);
  const retreat = useCallback(() => setIndex((i) => (i - 1 + total) % total), [total]);

  // Manual navigation — pauses auto-play
  const manualNext = useCallback(() => { setPlaying(false); advance(); }, [advance]);
  const manualPrev = useCallback(() => { setPlaying(false); retreat(); }, [retreat]);

  // Native Fullscreen API — with webkit fallback for Safari/iOS
  const toggleFullscreen = useCallback(async () => {
    const el = containerRef.current;
    if (!el) return;
    try {
      if (!document.fullscreenElement && !(document as Document & { webkitFullscreenElement?: Element }).webkitFullscreenElement) {
        await (el.requestFullscreen?.() ?? (el as HTMLDivElement & { webkitRequestFullscreen?(): Promise<void> }).webkitRequestFullscreen?.());
      } else {
        await (document.exitFullscreen?.() ?? (document as Document & { webkitExitFullscreen?(): Promise<void> }).webkitExitFullscreen?.());
      }
    } catch { /* user or browser denied fullscreen request */ }
  }, []);

  // Sync fullscreen state from browser events — covers Escape, browser controls, and our own button
  useEffect(() => {
    function onFSChange() {
      const isFS = !!(document.fullscreenElement ?? (document as Document & { webkitFullscreenElement?: Element }).webkitFullscreenElement);
      setFullscreen(isFS);
    }
    document.addEventListener('fullscreenchange', onFSChange);
    document.addEventListener('webkitfullscreenchange', onFSChange);
    return () => {
      document.removeEventListener('fullscreenchange', onFSChange);
      document.removeEventListener('webkitfullscreenchange', onFSChange);
    };
  }, []);

  // Keyboard shortcuts — Escape is handled natively by the Fullscreen API, don't intercept it
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'ArrowLeft') manualPrev();
      else if (e.key === 'ArrowRight') manualNext();
      else if (e.key === ' ') { e.preventDefault(); setPlaying((v) => !v); }
      else if (e.key === 'f') toggleFullscreen();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [manualPrev, manualNext, toggleFullscreen]);

  // Auto-advance timer — images only; resets whenever index or playing changes
  useEffect(() => {
    if (!playing) return;
    if (!current.mimetype.startsWith('image/')) return;
    const id = setTimeout(advance, 4000);
    return () => clearTimeout(id);
  }, [playing, index, advance, current.mimetype]);

  // Progress bar — mirrors the timer; double-rAF lets the DOM paint at 0% before transitioning
  const isImage = current.mimetype.startsWith('image/');
  useEffect(() => {
    setBarActive(false);
    if (!playing || !isImage) return;
    let raf1: number, raf2: number;
    raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setBarActive(true));
    });
    return () => { cancelAnimationFrame(raf1); cancelAnimationFrame(raf2); };
  }, [playing, index, isImage]);

  // Load the Cast SDK once on mount. The SDK calls window.__onGCastApiAvailable when ready.
  // Only works in Chrome with the Cast extension / a Chromecast on the local network.
  useEffect(() => {
    window.__onGCastApiAvailable = (isAvailable: boolean) => {
      if (!isAvailable) return;
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const cast = (window as any).cast;
        const ctx = cast.framework.CastContext.getInstance();
        ctx.setOptions({
          receiverApplicationId: cast.framework.CastContext.DEFAULT_MEDIA_RECEIVER_APP_ID,
          autoJoinPolicy: cast.framework.AutoJoinPolicy.ORIGIN_SCOPED,
        });
        setCastAvailable(true);
      } catch { /* Cast init failed — extension absent or policy blocked */ }
    };

    if (!document.querySelector('script[src*="cast_sender"]')) {
      const script = document.createElement('script');
      script.src = 'https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1';
      script.async = true;
      document.head.appendChild(script);
    }

    return () => { delete window.__onGCastApiAvailable; };
  }, []);

  // When the slide changes while a Cast session is active, push the new media to the receiver
  useEffect(() => {
    if (!castAvailable) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { cast, chrome: ch } = window as any;
      const session = cast.framework.CastContext.getInstance().getCurrentSession();
      if (!session) return;
      const mediaInfo = new ch.cast.media.MediaInfo(current.filepath, current.mimetype);
      mediaInfo.metadata = new ch.cast.media.GenericMediaMetadata();
      mediaInfo.metadata.title = current.original_filename;
      const request = new ch.cast.media.LoadRequest(mediaInfo);
      session.loadMedia(request).catch(() => { /* session may have ended */ });
    } catch { /* Cast not active */ }
  }, [castAvailable, index, current.filepath, current.mimetype, current.original_filename]);

  function renderMedia(item: SlideshowItem) {
    const mime = item.mimetype;
    if (mime.startsWith('image/')) {
      return (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={item.filepath}
          alt={item.original_filename}
          className="max-h-full max-w-full object-contain select-none"
          draggable={false}
        />
      );
    }
    if (mime.startsWith('video/')) {
      return (
        <video
          key={item.filepath}
          src={item.filepath}
          controls
          autoPlay
          className="max-h-full max-w-full"
          playsInline
          onEnded={playing ? advance : undefined}
        />
      );
    }
    if (mime.startsWith('audio/')) {
      return (
        <div className="flex flex-col items-center gap-4 p-8">
          <svg className="text-info" width="64" height="64" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
          </svg>
          <p className="text-txt text-sm text-center">{item.original_filename}</p>
          <audio
            key={item.filepath}
            src={item.filepath}
            controls
            autoPlay
            className="w-full max-w-md"
            onEnded={playing ? advance : undefined}
          />
        </div>
      );
    }
    return (
      <div className="text-muted text-sm p-8 text-center">
        <p>Cannot preview this file type.</p>
        <a href={item.filepath} target="_blank" rel="noopener noreferrer"
          className="text-accent hover:text-accent-hover mt-2 inline-block">
          Open file ↗
        </a>
      </div>
    );
  }

  const wrapperClass = fullscreen
    ? 'flex flex-col bg-black w-full h-full'
    : 'flex flex-col bg-base rounded-lg overflow-hidden border border-border';

  return (
    <div ref={containerRef} className={wrapperClass} role="region" aria-label="Slideshow player">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-card/90 border-b border-border shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm text-muted truncate">{batchName}</span>
          <span className="hidden sm:block text-[10px] text-faint/60 shrink-0 select-none" aria-hidden="true">
            ← → navigate · Space play/pause · F fullscreen
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span
            className="text-xs text-muted"
            aria-live="polite"
            aria-atomic="true"
            aria-label={`Slide ${index + 1} of ${total}`}
          >
            {index + 1} / {total}
          </span>
          <button onClick={() => setPlaying((v) => !v)}
            className="btn-icon p-1"
            aria-label={playing ? 'Pause' : 'Play'}
            aria-pressed={playing}
            aria-keyshortcuts="Space">
            {playing ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
            )}
          </button>
          {castAvailable && (
            <google-cast-launcher
              className="btn-icon p-1 w-8 h-8 cursor-pointer"
              title="Cast to TV"
              aria-label="Cast to TV"
            />
          )}
          <button onClick={toggleFullscreen}
            className="btn-icon p-1"
            aria-label={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            aria-pressed={fullscreen}
            aria-keyshortcuts="f">
            {fullscreen ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Main display */}
      <div className="flex-1 flex items-center justify-center relative overflow-hidden min-h-0 bg-black">
        {/* Prev button */}
        {total > 1 && (
          <button onClick={manualPrev}
            className="absolute left-2 z-10 p-2 rounded-full bg-black/50 text-white hover:bg-black/80 transition-colors"
            aria-label="Previous"
            aria-keyshortcuts="ArrowLeft">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
        )}

        {/* Media */}
        <div className="flex items-center justify-center w-full h-full p-2">
          {renderMedia(current)}
        </div>

        {/* Next button */}
        {total > 1 && (
          <button onClick={manualNext}
            className="absolute right-2 z-10 p-2 rounded-full bg-black/50 text-white hover:bg-black/80 transition-colors"
            aria-label="Next"
            aria-keyshortcuts="ArrowRight">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>
        )}

        {/* Progress bar — images only */}
        {isImage && playing && (
          <div className="absolute bottom-0 left-0 h-0.5 bg-accent"
            style={{ width: barActive ? '100%' : '0%', transition: barActive ? 'width 4s linear' : 'none' }}
            aria-hidden
          />
        )}
      </div>

      {/* Caption */}
      <div className="px-4 py-2 bg-card/90 border-t border-border shrink-0">
        <p className="text-xs text-muted truncate text-center">{current.original_filename}</p>
      </div>

      {/* Thumbnail strip */}
      {total > 1 && (
        <div className="flex gap-1.5 px-3 py-2 overflow-x-auto no-scrollbar bg-card shrink-0">
          {items.map((item, i) => (
            <button key={i} onClick={() => { setPlaying(false); setIndex(i); }}
              className={`shrink-0 w-12 h-9 rounded border-2 overflow-hidden transition-all ${
                i === index ? 'border-accent' : 'border-transparent opacity-60 hover:opacity-100'
              }`}
              aria-label={`Go to ${item.original_filename}`}
              aria-current={i === index ? 'true' : undefined}
            >
              {item.mimetype.startsWith('image/') ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={item.filepath} alt="" className="w-full h-full object-cover" loading="lazy" />
              ) : (
                <div className="w-full h-full bg-thumb flex items-center justify-center text-muted text-xs">
                  {item.mimetype.startsWith('video/') ? '▶' : item.mimetype.startsWith('audio/') ? '♪' : '?'}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
