'use client';

const PUBLIC_BASE = 'https://vid.arc-codex.com';

interface ShareToggleButtonProps {
  batchId: string;
  isShared: boolean;
  shareToken?: string;
}

export function ShareToggleButton({ batchId, isShared, shareToken }: ShareToggleButtonProps) {
  const publicUrl = isShared && shareToken
    ? `${PUBLIC_BASE}/public/batch/${shareToken}`
    : null;

  async function handleToggle() {
    try {
      await fetch(`/api/flask/batch/${batchId}/toggle_share`, {
        method: 'POST',
        credentials: 'include',
        body: new FormData(),
        redirect: 'manual',
      });
    } catch {
      // opaque redirect — ignore
    } finally {
      window.location.reload();
    }
  }

  return (
    <>
      {publicUrl && (
        <a href={publicUrl} target="_blank" rel="noopener noreferrer"
          className="btn-ghost text-sm" aria-label="Open public share link in new tab">
          Public link ↗
        </a>
      )}
      <button
        type="button"
        onClick={handleToggle}
        className={isShared ? 'btn-ghost text-sm text-danger/80 hover:text-danger' : 'btn-ghost text-sm'}
      >
        {isShared ? 'Unshare' : 'Share'}
      </button>
    </>
  );
}
