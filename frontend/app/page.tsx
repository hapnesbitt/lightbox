import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { getBatches } from '@/lib/flask';
import { BatchCard } from '@/components/BatchCard';
import { UploadDrawer } from '@/components/UploadDrawer';
import type { Metadata } from 'next';

export const metadata: Metadata = { title: 'My Library' };

export default async function HomePage() {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  const data = await getBatches(cookieHeader);
  if (!data) redirect('/login');

  const { batches } = data;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">My Library</h1>
        {batches.length > 0 && (
          <span className="badge-muted badge">{batches.length} batch{batches.length !== 1 ? 'es' : ''}</span>
        )}
      </div>

      <UploadDrawer batches={batches} />

      <section aria-label="Your library">
        {batches.length === 0 ? (
          <div className="empty-state">
            <svg className="empty-state-icon" width="48" height="48" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <p className="empty-state-title">No batches yet</p>
            <p className="empty-state-desc">Upload some media to create your first batch.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-3">
            {batches.map((batch) => (
              <BatchCard key={batch.id} batch={batch} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
