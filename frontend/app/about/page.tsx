import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'About LightBox',
  description: 'Features, technology, and the story behind LightBox.',
};

export default function AboutPage() {
  return (
    <div className="page-container max-w-3xl">

      {/* Hero */}
      <div className="page-header">
        <h1 className="page-title">About LightBox</h1>
      </div>
      <p className="text-muted text-sm mb-8">
        Create, manage, and share beautiful media slideshows — on hardware you control.
      </p>

      {/* Intro */}
      <div className="card p-6 mb-6">
        <p className="text-txt leading-relaxed">
          LightBox is a web application designed to make the creation, management, and sharing of
          media slideshows both simple and elegant. Whether you&apos;re a hobbyist archiving cherished
          memories, an artist showcasing a portfolio, or a developer exploring a full-stack media
          pipeline, LightBox offers a modern feature set built on Flask, Celery, Redis, FFmpeg, and
          Next.js.
        </p>
      </div>

      {/* Why Try LightBox */}
      <h2 className="text-sm font-semibold text-txt uppercase tracking-wide mb-3">
        Why try LightBox?
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
        {[
          {
            heading: 'Simplicity first',
            body: 'An intuitive interface for uploading, organising, and playing your media — no technical knowledge required.',
          },
          {
            heading: 'Versatile media handling',
            body: 'Seamlessly handles images, videos (MKV → MP4 conversion), and audio files (M4A archival transcoding).',
          },
          {
            heading: 'Optimised performance',
            body: 'Background processing keeps the UI snappy while FFmpeg handles demanding conversion tasks.',
          },
          {
            heading: 'Learn & explore',
            body: 'A real-world example of Flask + Celery + Redis + FFmpeg wired to a Next.js frontend.',
          },
        ].map(({ heading, body }) => (
          <div key={heading} className="card p-4">
            <h3 className="text-sm font-semibold text-txt mb-1">{heading}</h3>
            <p className="text-sm text-muted leading-relaxed">{body}</p>
          </div>
        ))}
      </div>

      {/* The cloud tax */}
      <h2 className="text-sm font-semibold text-txt uppercase tracking-wide mb-3">
        Save 98% — the cloud tax is real
      </h2>
      <div className="card p-5 mb-3">
        <p className="text-muted text-sm leading-relaxed mb-4">
          Disk drives are extraordinarily affordable; cloud storage is not. Here&apos;s a
          side-by-side for 20 TB over five years:
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div className="rounded-lg border border-accent/40 bg-accent/5 p-4">
            <p className="font-semibold text-accent mb-2">LightBox on your own hardware</p>
            <ul className="text-muted space-y-1">
              <li>~$100 / month — 20 TB usable, 5-year warranty</li>
              <li>Your data stays on hardware you control</li>
              <li>MKV → MP4 conversion included, free</li>
            </ul>
          </div>
          <div className="rounded-lg border border-danger/40 bg-danger/5 p-4">
            <p className="font-semibold text-danger mb-2">Equivalent cloud storage</p>
            <ul className="text-muted space-y-1">
              <li>$1,800 – $2,100 / month for the same capacity</li>
              <li>$108,000 – $126,000 total over 5 years</li>
              <li>Endless upsells for features we include free</li>
            </ul>
          </div>
        </div>
      </div>
      <div className="card p-4 mb-8">
        <h3 className="text-sm font-semibold text-txt mb-2">Why this makes sense for everyone</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm text-muted">
          <div>
            <p className="font-medium text-txt mb-1">For photographers &amp; creators</p>
            <ul className="space-y-1">
              <li>98 % savings vs. cloud providers</li>
              <li>Complete control of your media library</li>
              <li>No more &quot;storage full&quot; notifications</li>
            </ul>
          </div>
          <div>
            <p className="font-medium text-txt mb-1">For our community</p>
            <ul className="space-y-1">
              <li>Profits reinvested into computer education</li>
              <li>Computer recycling centres run as non-profits</li>
              <li>Local tech jobs, not Silicon Valley mansions</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Getting started */}
      <h2 className="text-sm font-semibold text-txt uppercase tracking-wide mb-3">
        Getting started
      </h2>
      <div className="card p-5 mb-8 space-y-4">
        {[
          ['Upload your media', 'Select images (JPG, PNG), videos (MP4, MOV, WebM, MKV), or audio (MP3, WAV, M4A, FLAC). Create a new batch or add to an existing one.'],
          ['View your gallery', 'Media items are displayed with their processing status. Hide, unhide, or mark favourites as needed.'],
          ['Launch the slideshow', 'Click Play to view your media in a full-featured presentation with fullscreen, keyboard, and touch navigation.'],
          ['Manage & share', 'Rename batches, add files, export data, or generate public share links to showcase your collections.'],
        ].map(([step, desc], i) => (
          <div key={step} className="flex gap-3">
            <span className="shrink-0 w-6 h-6 rounded-full bg-accent/15 text-accent text-xs font-bold flex items-center justify-center mt-0.5">
              {i + 1}
            </span>
            <div>
              <p className="text-sm font-semibold text-txt">{step}</p>
              <p className="text-sm text-muted leading-relaxed">{desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* MKV conversion */}
      <h2 className="text-sm font-semibold text-txt uppercase tracking-wide mb-3">
        MKV file uploads
      </h2>
      <div className="card p-5 mb-6">
        <p className="text-sm text-muted leading-relaxed mb-3">
          LightBox accepts MKV files. Because not all browsers play them natively, we automatically
          convert them to a universally compatible MP4 (H.264 video, AAC audio) in the background.
          You&apos;ll see a &ldquo;Processing&rdquo; status while conversion runs — the original MKV is preserved.
        </p>
        <p className="text-xs text-muted mb-2">Typical FFmpeg command:</p>
        <pre className="bg-surface rounded-md p-3 text-xs text-txt overflow-x-auto leading-relaxed">
          <code>{`ffmpeg -i [input.mkv] \\
    -c:v libx264 -preset medium -crf 22 \\
    -c:a aac -b:a 128k \\
    -movflags +faststart -y [output.mp4]`}</code>
        </pre>
      </div>

      {/* Archival audio */}
      <h2 className="text-sm font-semibold text-txt uppercase tracking-wide mb-3">
        Archival audio quality (M4A)
      </h2>
      <div className="card p-5 mb-8">
        <p className="text-sm text-muted leading-relaxed mb-3">
          Uploads like M4A, WAV, or FLAC are transcoded to high-quality M4A (AAC) using{' '}
          <code className="text-xs bg-surface px-1 py-0.5 rounded">libfdk_aac</code> when
          available — ideal for playback and long-term archival. MP3 and OGG are stored as-is to
          prevent re-encoding quality loss.
        </p>
        <p className="text-xs text-muted mb-2">Typical FFmpeg command:</p>
        <pre className="bg-surface rounded-md p-3 text-xs text-txt overflow-x-auto leading-relaxed">
          <code>{`ffmpeg -i [input_audio] \\
    -c:a libfdk_aac -vbr 5 -ar 48000 \\
    -y [output.m4a]`}</code>
        </pre>
      </div>

      {/* AI collaborator */}
      <h2 className="text-sm font-semibold text-txt uppercase tracking-wide mb-3">
        AI collaborator
      </h2>
      <div className="card p-5 mb-8">
        <p className="text-sm text-muted leading-relaxed mb-2">
          LightBox was built in close collaboration with AI language models (Google Gemini and
          Anthropic Claude). The AI contributed code suggestions, state-management patterns, and
          problem-solving — particularly for the slideshow viewer and the Next.js frontend rewrite.
        </p>
        <p className="text-sm text-muted leading-relaxed italic">
          Ross is the one who integrates, tests, and brings it all to life in the actual application.
          Teamwork makes the dream work.
        </p>
      </div>

      {/* Open source */}
      <h2 className="text-sm font-semibold text-txt uppercase tracking-wide mb-3">
        Open source &amp; contribution
      </h2>
      <div className="card p-5 mb-8 space-y-2">
        <p className="text-sm text-muted leading-relaxed mb-3">
          LightBox is open-source and a great educational showcase of Flask, Celery, Redis, FFmpeg,
          Bootstrap, and modern JavaScript. Dive in, experiment, and contribute!
        </p>
        {[
          ['View source on GitHub', 'Explore the codebase and clone it.', 'https://github.com/hapnesbitt/lightbox'],
          ['Read the README', 'Setup instructions (Flask & Docker).', 'https://github.com/hapnesbitt/lightbox/blob/main/README.md'],
          ['How to contribute', 'Learn how you can help improve LightBox.', 'https://github.com/hapnesbitt/lightbox/blob/main/CONTRIBUTING.md'],
          ['Report an issue', 'Your feedback is invaluable.', 'https://github.com/hapnesbitt/lightbox/issues'],
        ].map(([label, sub, href]) => (
          <a
            key={label}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col px-3 py-2 rounded border border-border hover:border-faint hover:bg-card-hover transition-colors"
          >
            <span className="text-sm font-medium text-txt">{label}</span>
            <span className="text-xs text-muted">{sub}</span>
          </a>
        ))}
      </div>

      {/* Author */}
      <div className="card p-5 mb-8 text-center">
        <p className="text-sm text-muted">
          Primarily developed by <span className="font-semibold text-txt">Ross Nesbitt</span>.
          Built on the shoulders of Flask, Celery, Redis, Bootstrap, Jinja2, FFmpeg, and Next.js.
          A massive thank you to their communities.
        </p>
      </div>

      <div className="text-center mb-4">
        <Link href="/" className="btn-ghost text-sm px-4 py-2">
          ← Back to my library
        </Link>
      </div>
    </div>
  );
}
