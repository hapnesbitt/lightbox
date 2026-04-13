'use client';

import { useState, useRef, useCallback } from 'react';
import type { Batch } from '@/lib/types';

interface UploadAreaProps {
  batches: Batch[];
}

const UPLOAD_TYPES = [
  { value: 'media', label: 'Media (auto-convert)' },
  { value: 'blob_storage', label: 'Files (store as-is)' },
  { value: 'import_zip', label: 'ZIP archive' },
];

export function UploadArea({ batches }: UploadAreaProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [batchMode, setBatchMode] = useState<'new' | 'existing'>('new');
  const [newBatchName, setNewBatchName] = useState('');
  const [existingBatchId, setExistingBatchId] = useState('');
  const [uploadType, setUploadType] = useState('media');
  const [uploading, setUploading] = useState(false);

  const addFiles = useCallback((incoming: FileList | null) => {
    if (!incoming) return;
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name + f.size));
      const fresh = Array.from(incoming).filter((f) => !existing.has(f.name + f.size));
      return [...prev, ...fresh];
    });
  }, []);

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragging(true);
  }
  function onDragLeave() { setDragging(false); }
  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (files.length === 0) return;
    setUploading(true);

    const formData = new FormData();
    formData.set('upload_type', uploadType);
    if (batchMode === 'new') {
      formData.set('batch_name', newBatchName.trim());
    } else {
      formData.set('existing_batch_id', existingBatchId);
    }
    for (const file of files) {
      formData.append('files[]', file);
    }

    try {
      await fetch('/api/flask/upload', {
        method: 'POST',
        credentials: 'include',
        body: formData,
        redirect: 'manual',
      });
    } finally {
      setUploading(false);
      window.location.reload();
    }
  }

  const destinationName =
    batchMode === 'new'
      ? newBatchName.trim()
      : batches.find((b) => b.id === existingBatchId)?.name ?? '';

  const totalSize = files.reduce((s, f) => s + f.size, 0);
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  return (
    <form onSubmit={handleSubmit} className="card p-5 space-y-4">
      <h2 className="text-sm font-semibold text-txt uppercase tracking-wide">Upload media</h2>

      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop files here or click to browse"
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragging ? 'drop-zone-active' : 'border-border hover:border-faint'
        }`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInputRef.current?.click()}
      >
        <svg className="mx-auto mb-2 text-muted" width="32" height="32" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <p className="text-sm text-muted">Drop files here or <span className="text-accent">browse</span></p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          accept="video/*,video/mp4,video/webm,video/x-matroska,video/quicktime,video/x-msvideo,audio/*,image/*,application/pdf,application/zip,.mp4,.webm,.mkv,.mov,.avi,.wmv,.flv,.mpg,.mpeg,.mp3,.aac,.wav,.ogg,.opus,.flac,.m4a,.wma,.jpg,.jpeg,.png,.gif,.webp,.bmp,.pdf,.zip"
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <ul className="space-y-1 max-h-40 overflow-y-auto">
          {files.map((f, i) => (
            <li key={i} className="flex items-center justify-between gap-2 text-sm py-1 px-2 rounded hover:bg-card-hover">
              <span className="truncate text-txt">{f.name}</span>
              <span className="text-muted shrink-0">{formatSize(f.size)}</span>
              <button type="button" onClick={() => removeFile(i)}
                className="text-muted hover:text-danger shrink-0 ml-1" aria-label={`Remove ${f.name}`}>
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      {files.length > 1 && (
        <p className="text-xs text-muted">{files.length} files · {formatSize(totalSize)} total</p>
      )}

      {/* Upload type */}
      <div className="flex gap-2 flex-wrap">
        {UPLOAD_TYPES.map(({ value, label }) => (
          <button key={value} type="button"
            className={`px-3 py-1 text-xs rounded border transition-colors ${
              uploadType === value
                ? 'border-accent text-accent bg-accent/10'
                : 'border-border text-muted hover:border-faint hover:text-txt'
            }`}
            aria-pressed={uploadType === value}
            onClick={() => setUploadType(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Batch target */}
      <div className="flex gap-2">
        <button type="button"
          className={`px-3 py-1 text-xs rounded border transition-colors ${batchMode === 'new' ? 'border-accent text-accent bg-accent/10' : 'border-border text-muted hover:border-faint'}`}
          aria-pressed={batchMode === 'new'}
          onClick={() => setBatchMode('new')}
        >New batch</button>
        {batches.length > 0 && (
          <button type="button"
            className={`px-3 py-1 text-xs rounded border transition-colors ${batchMode === 'existing' ? 'border-accent text-accent bg-accent/10' : 'border-border text-muted hover:border-faint'}`}
            aria-pressed={batchMode === 'existing'}
            onClick={() => setBatchMode('existing')}
          >Add to existing</button>
        )}
      </div>

      {batchMode === 'new' ? (
        <input
          type="text"
          value={newBatchName}
          onChange={(e) => setNewBatchName(e.target.value)}
          placeholder={uploadType === 'import_zip' ? 'Batch name (optional for ZIP)' : 'Batch name'}
          className="input"
          aria-label="New batch name"
        />
      ) : (
        <select
          value={existingBatchId}
          onChange={(e) => setExistingBatchId(e.target.value)}
          className="input"
          aria-label="Select an existing batch"
        >
          <option value="">— Select a batch —</option>
          {batches.map((b) => (
            <option key={b.id} value={b.id}>{b.name} ({b.itemCount} items)</option>
          ))}
        </select>
      )}

<button type="submit" disabled={uploading || files.length === 0} className="btn-primary w-full">
        {uploading
          ? 'Uploading…'
          : files.length === 0
          ? 'Upload'
          : destinationName
          ? `Upload ${files.length} ${files.length === 1 ? 'file' : 'files'} to ${destinationName}`
          : `Upload ${files.length} ${files.length === 1 ? 'file' : 'files'}`}
      </button>
    </form>
  );
}
