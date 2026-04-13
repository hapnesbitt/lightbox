import { notFound } from 'next/navigation';
import Link from 'next/link';
import { getPublicBatch } from '@/lib/flask';
import type { MediaItem } from '@/lib/types';
import type { Metadata } from 'next';

interface Props {
  params: Promise<{ token: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { token } = await params;
  const batch = await getPublicBatch(token);
  return { title: batch ? `${batch.name} (Public)` : 'Shared Collection' };
}

function PublicMediaThumb({ item }: { item: MediaItem }) {
  const mime = item.mimetype ?? '';
  if (mime.startsWith('image/') && item.web_path) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={item.web_path} alt={item.original_filename} loading="lazy"
        className="w-full h-full object-cover" />
    );
  }
  if (mime.startsWith('video/')) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-thumb">
        <svg className="text-accent" width="24" height="24" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/>
        </svg>
      </div>
    );
  }
  if (mime.startsWith('audio/')) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-thumb">
        <svg className="text-info" width="24" height="24" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
        </svg>
      </div>
    );
  }
  return (
    <div className="w-full h-full flex items-center justify-center bg-thumb">
      <svg className="text-muted" width="24" height="24" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
    </div>
  );
}

export default async function PublicBatchPage({ params }: Props) {
  const { token } = await params;
  const batch = await getPublicBatch(token);

  if (!batch) notFound();

  const playableCount = batch.media.filter(
    (m) => m.item_type === 'media' && m.web_path &&
      (m.mimetype?.startsWith('image/') || m.mimetype?.startsWith('video/') || m.mimetype?.startsWith('audio/'))
  ).length;

  return (
    <div className="page-container">
      <div className="page-header flex-wrap gap-2">
        <div className="min-w-0">
          <h1 className="page-title truncate">{batch.name}</h1>
          <p className="text-sm text-muted mt-0.5">{batch.media.length} item{batch.media.length !== 1 ? 's' : ''}</p>
        </div>
        {playableCount > 0 && (
          <Link href={`/public/slideshow/${token}`} className="btn-primary text-sm shrink-0"
            aria-label={`Play slideshow — ${playableCount} item${playableCount === 1 ? '' : 's'}`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            Slideshow
          </Link>
        )}
      </div>

      {batch.media.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state-title">Nothing here yet</p>
          <p className="empty-state-desc">This shared lightbox is empty or not yet available. If someone sent you this link, the owner may still be adding content.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3">
          {batch.media.map((item) => (
            <div key={item.id} className="card rounded-lg overflow-hidden">
              <div className="media-thumb rounded-none">
                {item.web_path ? (
                  <a href={item.web_path} target="_blank" rel="noopener noreferrer" className="block w-full h-full">
                    <PublicMediaThumb item={item} />
                  </a>
                ) : (
                  <PublicMediaThumb item={item} />
                )}
              </div>
              <div className="p-2">
                <p className="text-xs text-txt truncate" title={item.original_filename}>
                  {item.original_filename}
                </p>
                {item.download_url && item.item_type === 'blob' && (
                  <a href={`/api/flask${item.download_url}`} download
                    className="text-xs text-accent hover:text-accent-hover mt-1 inline-block">
                    Download
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <footer className="mt-12 text-center text-xs text-muted">
        Shared via{' '}
        <Link href="/" className="text-accent hover:text-accent-hover">LightBox</Link>
      </footer>
    </div>
  );
}
