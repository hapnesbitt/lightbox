import { notFound } from 'next/navigation';
import Link from 'next/link';
import { getPublicSlideshow } from '@/lib/flask';
import { SlideshowPlayer } from '@/components/SlideshowPlayer';
import type { Metadata } from 'next';

interface Props {
  params: Promise<{ token: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { token } = await params;
  const data = await getPublicSlideshow(token);
  return { title: data ? `${data.batchName} (Public Slideshow)` : 'Shared Slideshow' };
}

export default async function PublicSlideshowPage({ params }: Props) {
  const { token } = await params;
  const data = await getPublicSlideshow(token);

  if (!data) notFound();

  if (data.items.length === 0) {
    return (
      <div className="page-container">
        <div className="empty-state">
          <p className="empty-state-title">No playable items</p>
          <Link href={`/public/batch/${token}`} className="btn-primary mt-2">View collection</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="mb-4">
        <Link href={`/public/batch/${token}`}
          className="flex items-center gap-2 text-muted hover:text-txt transition-colors text-sm w-fit"
          aria-label={`Back to ${data.batchName}`}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          {data.batchName}
        </Link>
      </div>
      <SlideshowPlayer items={data.items} batchName={data.batchName} />
    </div>
  );
}
