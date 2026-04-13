'use client';

import { useState, useRef, useEffect } from 'react';
import type { MediaItem } from '@/lib/types';

interface MediaCardProps {
  item: MediaItem;
  batchId: string;
  onToggleHidden?: (id: string, hidden: boolean) => void;
  onToggleLiked?: (id: string, liked: boolean) => void;
  onDelete?: (id: string) => void;
}

function MediaThumb({ item }: { item: MediaItem }) {
  const mime = item.mimetype ?? '';
  if (item.item_type === 'blob') {
    return (
      <div className="media-thumb flex items-center justify-center">
        <svg className="text-muted" width="28" height="28" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <span className="badge-muted badge absolute bottom-1.5 left-1.5 text-xs">File</span>
      </div>
    );
  }

  if (item.processing_status === 'queued' || item.processing_status === 'processing') {
    return (
      <div className="media-thumb flex items-center justify-center">
        <div className="animate-spin rounded-full h-7 w-7 border-2 border-accent border-t-transparent" />
        <span className="badge badge-warning absolute bottom-1.5 left-1.5 text-xs capitalize">
          {item.processing_status}
        </span>
      </div>
    );
  }

  if (item.processing_status === 'failed') {
    return (
      <div className="media-thumb flex items-center justify-center">
        <svg className="text-danger" width="28" height="28" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="12" cy="12" r="10"/>
          <line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        <span className="badge badge-danger absolute bottom-1.5 left-1.5 text-xs">Failed</span>
      </div>
    );
  }

  if (mime.startsWith('image/') && item.web_path) {
    return (
      <div className="media-thumb">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={item.web_path} alt={item.original_filename} loading="lazy" />
        <span className="badge badge-accent absolute bottom-1.5 left-1.5 text-xs">Image</span>
      </div>
    );
  }

  if (mime.startsWith('video/')) {
    return (
      <div className="media-thumb flex items-center justify-center">
        <svg className="text-accent" width="28" height="28" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/>
        </svg>
        <span className="badge badge-accent absolute bottom-1.5 left-1.5 text-xs">Video</span>
      </div>
    );
  }

  if (mime.startsWith('audio/')) {
    return (
      <div className="media-thumb flex items-center justify-center">
        <svg className="text-info" width="28" height="28" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
        </svg>
        <span className="badge badge-info absolute bottom-1.5 left-1.5 text-xs">Audio</span>
      </div>
    );
  }

  if (mime === 'application/pdf') {
    return (
      <div className="media-thumb flex items-center justify-center">
        <svg className="text-danger" width="28" height="28" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        <span className="badge badge-danger absolute bottom-1.5 left-1.5 text-xs">PDF</span>
      </div>
    );
  }

  return (
    <div className="media-thumb flex items-center justify-center">
      <svg className="text-muted" width="24" height="24" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
        <polyline points="13 2 13 9 20 9"/>
      </svg>
    </div>
  );
}

export function MediaCard({ item, batchId, onToggleHidden, onToggleLiked, onDelete }: MediaCardProps) {
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(item.is_hidden ?? false);
  const [liked, setLiked] = useState(item.is_liked ?? false);
  const [deleted, setDeleted] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => { if (deleteTimerRef.current) clearTimeout(deleteTimerRef.current); };
  }, []);

  if (deleted) return null;

  async function postAction(url: string) {
    setBusy(true);
    try {
      await fetch(`/api/flask${url}`, { method: 'POST', credentials: 'include', body: new FormData(), redirect: 'manual' });
    } catch { /* opaque redirect — ignore */ }
    finally {
      setBusy(false);
      window.location.reload();
    }
  }

  async function handleToggleHidden() {
    await postAction(`/media/${item.id}/toggle_hidden`);
    const next = !hidden;
    setHidden(next);
    onToggleHidden?.(item.id!, next);
  }

  async function handleToggleLiked() {
    await postAction(`/media/${item.id}/toggle_liked`);
    const next = !liked;
    setLiked(next);
    onToggleLiked?.(item.id!, next);
  }

  function requestDelete() {
    setConfirmDelete(true);
    deleteTimerRef.current = setTimeout(() => setConfirmDelete(false), 5000);
  }

  function cancelDelete() {
    if (deleteTimerRef.current) clearTimeout(deleteTimerRef.current);
    setConfirmDelete(false);
  }

  async function handleDelete() {
    if (deleteTimerRef.current) clearTimeout(deleteTimerRef.current);
    setConfirmDelete(false);
    await postAction(`/media/${item.id}/delete`);
  }

  const isProcessing = item.processing_status === 'queued' || item.processing_status === 'processing';
  const isDone = item.processing_status === 'completed' || item.processing_status === undefined;

  return (
    <div className={`card rounded-lg overflow-hidden ${hidden && isDone ? 'opacity-50' : ''}`}>
      {/* Thumbnail */}
      <div className="relative">
        <MediaThumb item={item} />
        {liked && isDone && (
          <div className="absolute top-1.5 right-1.5" aria-hidden="true">
            <span className="badge badge-warning text-xs">♥</span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-2">
        <p className="text-xs text-txt truncate mb-2" title={item.original_filename}>
          {item.original_filename}
        </p>

        {isDone && !isProcessing && (
          <div className="flex items-end gap-1 flex-wrap">
            {item.web_path && (
              <a href={item.web_path} target="_blank" rel="noopener noreferrer"
                className="btn-icon p-1 flex-col gap-0.5 h-auto" title="Open" aria-label="Open file">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                <span className="text-xs leading-none">Open</span>
              </a>
            )}
            {item.download_url && (
              <a href={`/api/flask${item.download_url}`} download
                className="btn-icon p-1 flex-col gap-0.5 h-auto" title="Download" aria-label="Download">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                <span className="text-xs leading-none">Save</span>
              </a>
            )}
            <button onClick={handleToggleLiked} disabled={busy}
              className={`btn-icon p-1 flex-col gap-0.5 h-auto ${liked ? 'text-warning' : ''}`}
              title={liked ? 'Unlike' : 'Like'} aria-label={liked ? 'Unlike' : 'Like'}>
              <span aria-hidden>♥</span>
              <span className="text-xs leading-none">Like</span>
            </button>
            <button onClick={handleToggleHidden} disabled={busy}
              className="btn-icon p-1 flex-col gap-0.5 h-auto" title={hidden ? 'Show' : 'Hide'} aria-label={hidden ? 'Show' : 'Hide'}>
              {hidden ? (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              ) : (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                  <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              )}
              <span className="text-xs leading-none">{hidden ? 'Show' : 'Hide'}</span>
            </button>
            {/* Divider before delete zone */}
            <span className="w-px h-8 bg-border self-center ml-auto mx-1 shrink-0" aria-hidden />

            {confirmDelete ? (
              <div className="flex items-center gap-1.5">
                <button
                  onClick={handleDelete}
                  disabled={busy}
                  className="text-[10px] text-faint/60 hover:text-muted/80 transition-colors cursor-pointer leading-none px-0.5"
                  aria-label="Confirm delete forever"
                >
                  Delete forever
                </button>
                <button
                  onClick={cancelDelete}
                  className="inline-flex items-center justify-center text-xs font-medium text-txt border border-border rounded px-2 py-0.5 bg-card hover:bg-card-hover hover:border-faint transition-all cursor-pointer"
                  aria-label="Cancel delete"
                >
                  Keep it
                </button>
              </div>
            ) : (
              <button
                onClick={requestDelete}
                disabled={busy}
                className="flex flex-col items-center gap-0.5 text-muted/50 hover:text-muted transition-colors p-1 rounded"
                title="Delete"
                aria-label="Delete"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                </svg>
                <span className="text-xs leading-none">Delete</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
