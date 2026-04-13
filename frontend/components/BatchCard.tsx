'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import type { Batch } from '@/lib/types';

interface BatchCardProps {
  batch: Batch;
}

export function BatchCard({ batch }: BatchCardProps) {
  const [deleted, setDeleted] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const deleteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    return () => { if (deleteTimerRef.current) clearTimeout(deleteTimerRef.current); };
  }, []);

  // Move focus to "Keep it" when confirmation appears so AT announces it immediately
  useEffect(() => {
    if (confirmDelete) cancelBtnRef.current?.focus();
  }, [confirmDelete]);

  if (deleted) return null;

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
    setBusy(true);
    try {
      await fetch(`/api/flask/batch/${batch.id}/delete`, {
        method: 'POST',
        credentials: 'include',
        body: new FormData(),
        redirect: 'manual',
      });
    } catch { /* opaque redirect — ignore */ }
    finally {
      setBusy(false);
      window.location.reload();
    }
  }

  return (
    <div className="card rounded-lg overflow-hidden">
      <Link
        href={`/batch/${batch.id}`}
        className="block p-4 hover:bg-card-hover transition-colors duration-150 group"
      >
        {/* Thumbnail placeholder */}
        <div className="media-thumb rounded mb-3 bg-thumb flex items-center justify-center">
          <svg className="text-faint group-hover:text-muted transition-colors" width="36" height="36"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <rect x="2" y="2" width="20" height="20" rx="2.18"/>
            <line x1="7" y1="2" x2="7" y2="22"/>
            <line x1="17" y1="2" x2="17" y2="22"/>
            <line x1="2" y1="12" x2="22" y2="12"/>
            <line x1="2" y1="7" x2="7" y2="7"/>
            <line x1="2" y1="17" x2="7" y2="17"/>
            <line x1="17" y1="17" x2="22" y2="17"/>
            <line x1="17" y1="7" x2="22" y2="7"/>
          </svg>
        </div>

        <h3 className="font-medium text-txt text-sm truncate group-hover:text-accent-hover transition-colors">
          {batch.name}
        </h3>
        <p className="text-xs text-muted mt-0.5">
          {batch.itemCount} item{batch.itemCount !== 1 ? 's' : ''}
          {batch.isShared && <span className="ml-2 badge-accent badge">shared</span>}
        </p>
      </Link>

      {/* Delete zone */}
      <div className="flex items-center px-2 pb-2">
        <span className="w-px h-3 bg-border self-center ml-auto mx-1 shrink-0" aria-hidden />

        {confirmDelete ? (
          <div className="flex items-center gap-1.5" role="alert" aria-label="Delete confirmation">
            <button
              onClick={handleDelete}
              disabled={busy}
              className="text-[10px] text-faint/60 hover:text-muted/80 transition-colors cursor-pointer leading-none px-0.5"
              aria-label="Confirm delete forever"
            >
              Delete forever
            </button>
            <button
              ref={cancelBtnRef}
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
            className="text-muted/50 hover:text-muted transition-colors p-0.5 rounded leading-none"
            title="Delete batch"
            aria-label="Delete batch"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
