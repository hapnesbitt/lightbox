import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import Link from 'next/link';
import { getSlideshow } from '@/lib/flask';
import { SlideshowPlayer } from '@/components/SlideshowPlayer';
import type { Metadata } from 'next';

interface Props {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: 'Slideshow' };
}

export default async function SlideshowPage({ params }: Props) {
  const { id } = await params;
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  const data = await getSlideshow(id, cookieHeader);
  if (!data) redirect('/login');

  if (data.items.length === 0) {
    return (
      <div className="page-container">
        <div className="page-header">
          <Link href={`/batch/${id}`} className="text-muted hover:text-txt transition-colors" aria-label="Back to batch">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </Link>
          <h1 className="page-title">{data.batchName}</h1>
        </div>
        <div className="empty-state">
          <p className="empty-state-title">No ready media yet</p>
          <p className="empty-state-desc">Videos and audio may still be processing — check back in a few minutes. Images and PDFs are available immediately after upload.</p>
          <Link href={`/batch/${id}`} className="btn-primary mt-2">Back to batch</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header mb-4">
        <Link href={`/batch/${id}`} className="flex items-center gap-2 text-muted hover:text-txt transition-colors text-sm">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          {data.batchName}
        </Link>
      </div>
      <SlideshowPlayer items={data.items} batchName={data.batchName} />
    </div>
  );
}
