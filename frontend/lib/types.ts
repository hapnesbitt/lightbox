// TypeScript interfaces mirroring Flask/Redis data structures

export interface Batch {
  id: string;
  name: string;
  itemCount: number;
  creationTimestamp?: number;
  isShared?: boolean;
  shareToken?: string;
  validSlideshowCount?: number;
}

export interface MediaItem {
  id?: string;
  filepath: string;       // relative path: "username/batch_id/file.mp4"
  mimetype: string;       // "video/mp4", "image/jpeg", etc.
  original_filename: string;
  is_hidden?: boolean;
  is_liked?: boolean;
  processing_status?: 'completed' | 'queued' | 'processing' | 'failed';
  item_type?: 'media' | 'blob' | 'archive_import';
  upload_timestamp?: number;
  web_path?: string;      // "/static/uploads/..."
  download_url?: string;
  error_message?: string;
}

// From Flask's slideshow endpoint – embedded as JSON in script tag
export interface SlideshowItem {
  filepath: string;       // "/static/uploads/..."
  mimetype: string;
  original_filename: string;
}

export interface SessionUser {
  username: string;
  isAdmin?: boolean;
}
