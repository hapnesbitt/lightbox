'use client';

import { useState, useId } from 'react';
import { UploadArea } from '@/components/UploadArea';
import type { Batch } from '@/lib/types';

interface UploadDrawerProps {
  batches: Batch[];
}

export function UploadDrawer({ batches }: UploadDrawerProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <div className="mb-6">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full px-4 py-2.5 card rounded-lg text-sm font-medium text-muted hover:text-txt hover:bg-card-hover transition-colors"
        aria-expanded={open}
        aria-controls={panelId}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden
          className={`shrink-0 transition-transform duration-300 ${open ? 'rotate-45' : ''}`}>
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        Upload media
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden
          className={`ml-auto shrink-0 transition-transform duration-300 ${open ? '-rotate-180' : ''}`}>
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      {/* grid-template-rows trick: animates height without knowing the content height */}
      <div
        id={panelId}
        className={`grid transition-[grid-template-rows] duration-300 ease-in-out ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="overflow-hidden">
          <div className="pt-3">
            <UploadArea batches={batches} />
          </div>
        </div>
      </div>
    </div>
  );
}
