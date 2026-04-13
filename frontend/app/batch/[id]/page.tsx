import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import Link from 'next/link';
import { getBatchDetail } from '@/lib/flask';
import { MediaCard } from '@/components/MediaCard';
import { UploadDrawer } from '@/components/UploadDrawer';
import { ShareToggleButton } from '@/components/ShareToggleButton';
import type { Metadata } from 'next';

interface Props {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: `Batch ${id.slice(0, 8)}` };
}

export default async function BatchPage({ params }: Props) {
  const { id } = await params;
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  const batch = await getBatchDetail(id, cookieHeader);

  if (!batch) redirect('/login');

  const playableCount = batch.media.filter(
    (m) => m.item_type === 'media' && m.processing_status === 'completed' && !m.is_hidden && m.web_path
  ).length;

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header flex-wrap gap-2">
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/" className="text-muted hover:text-txt transition-colors shrink-0"
            aria-label="Back to library">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </Link>
          <h1 className="page-title truncate">{batch.name}</h1>
          {batch.isShared && <span className="badge-accent badge shrink-0">shared</span>}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <ShareToggleButton batchId={id} isShared={batch.isShared} shareToken={batch.shareToken} />
        </div>
      </div>

      {/* Slideshow hero banner */}
      {playableCount > 0 && (
        <Link
          href={`/slideshow/${id}`}
          className="flex items-center justify-center gap-3 w-full rounded-lg bg-orange-500 hover:bg-orange-600 transition-colors px-6 py-4 mb-6 text-white font-bold text-lg"
          aria-label={`Play slideshow — ${playableCount} item${playableCount === 1 ? '' : 's'}`}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="white"
            stroke="none" aria-hidden="true" className="shrink-0">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
          Play Slideshow · {playableCount} item{playableCount === 1 ? '' : 's'}
        </Link>
      )}

      <UploadDrawer batches={[{ id, name: batch.name, itemCount: batch.media.length }]} />

      <section aria-label="Media items">
        {batch.media.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-title">No items yet</p>
            <p className="empty-state-desc">Use the upload panel above to add media to this batch.</p>
          </div>
        ) : (
          <div role="list" className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-3">
            {batch.media.map((item) => (
              <div key={item.id} role="listitem">
                <MediaCard
                  item={item}
                  batchId={id}
                />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
