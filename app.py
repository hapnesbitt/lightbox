import datetime
import os
import uuid
import json
import shutil
import zipfile
from functools import wraps
from io import BytesIO
import logging
import secrets
import subprocess

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort, jsonify, current_app
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import redis
from urllib.parse import urlparse as url_parse
from celery import Celery
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file if present at the very start

# Initialize Flask app
app = Flask(__name__)
# IMPORTANT: Ensure FLASK_SECRET_KEY is set in your .env or environment
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'fallback_dev_secret_key_ ঊ<x_bin_118> ঊ CHANGE_IN_PROD')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 9000 * 1024 * 1024  # Approx 9GB
app.config['FFMPEG_PATH'] = os.environ.get('FFMPEG_PATH', 'ffmpeg')

# --- Audio Transcoding to MP3 Configuration ---
app.config['AUDIO_MP3_ENCODER'] = 'libmp3lame'
app.config['AUDIO_MP3_OPTIONS'] = os.environ.get('AUDIO_MP3_OPTIONS', '-q:a 0 -compression_level 0').split()
app.config['AUDIO_MP3_SAMPLE_RATE'] = os.environ.get('AUDIO_MP3_SAMPLE_RATE', '44100')
app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3'] = set(
    os.environ.get('AUDIO_FORMATS_TO_CONVERT_TO_MP3', 'wav,flac,m4a,aac,ogg,opus').lower().split(',')
)
# Ensure '' from empty string doesn't become an element
if '' in app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3'] and len(app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3']) == 1:
    app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3'] = set()

# --- Video Transcoding Configuration ---
app.config['VIDEO_MP4_VIDEO_CODEC'] = 'libx264'
app.config['VIDEO_MP4_VIDEO_PRESET'] = os.environ.get('VIDEO_MP4_VIDEO_PRESET', 'medium')
app.config['VIDEO_MP4_VIDEO_CRF'] = os.environ.get('VIDEO_MP4_VIDEO_CRF', '22')
app.config['VIDEO_MP4_AUDIO_CODEC'] = os.environ.get('VIDEO_MP4_AUDIO_CODEC', 'aac') # For video's audio track
app.config['VIDEO_MP4_AUDIO_BITRATE'] = os.environ.get('VIDEO_MP4_AUDIO_BITRATE', '128k')
app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4'] = set(
    os.environ.get('VIDEO_FORMATS_TO_CONVERT_TO_MP4', 'mkv,mov,avi,wmv,flv').lower().split(',')
)
if '' in app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4'] and len(app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4']) == 1:
    app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4'] = set()

# --- Application's Main Redis DB Number ---
app.config['APP_REDIS_DB_NUM'] = int(os.environ.get('APP_REDIS_DB_NUM', 0)) # For app data

# --- Celery Configuration ---
redis_password_for_celery = os.environ.get('REDIS_PASSWORD', None)
redis_host_for_celery = os.environ.get('REDIS_HOST', 'localhost')
redis_port_for_celery = int(os.environ.get('REDIS_PORT', 6379))
redis_auth_part = f":{redis_password_for_celery}@" if redis_password_for_celery else ""
CELERY_BROKER_URL_CONFIG = f"redis://{redis_auth_part}{redis_host_for_celery}:{redis_port_for_celery}/0" # Broker uses DB 0
CELERY_RESULT_BACKEND_CONFIG = f"redis://{redis_auth_part}{redis_host_for_celery}:{redis_port_for_celery}/1" # Results in DB 1

app.config.update(
    broker_url=CELERY_BROKER_URL_CONFIG,
    result_backend=CELERY_RESULT_BACKEND_CONFIG,
    task_track_started=True,
    # Consider adding these for robustness if tasks might get lost:
    # task_acks_late=True,
    # task_reject_on_worker_lost=True,
)
def make_celery(flask_app):
    celery_instance = Celery(
        flask_app.import_name,
        broker=flask_app.config['broker_url'],
        backend=flask_app.config['result_backend']
    )
    celery_instance.conf.update(flask_app.config) # Important for Celery to pick up other configs
    class ContextTask(celery_instance.Task):
        abstract = True
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)
    celery_instance.Task = ContextTask
    return celery_instance
celery = make_celery(app)

# --- Logging Setup ---
log_level_str = os.environ.get('LOG_LEVEL', 'INFO' if not app.debug else 'DEBUG').upper()
log_level = getattr(logging, log_level_str, logging.INFO)

if not app.logger.handlers: # Only add handler if flask didn't add one (e.g. when not in debug)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    app.logger.addHandler(stream_handler)
app.logger.setLevel(log_level)
# Also configure root logger if running with gunicorn and you want gunicorn logs to match format/level
if os.environ.get("FLASK_ENV") == "production": # Example condition for prod
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')


@app.context_processor
def inject_current_year():
    return {'current_year': datetime.datetime.now().year}

csrf = CSRFProtect(app)

# --- Redis Connection (for Flask App Data) ---
try:
    redis_client = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=app.config['APP_REDIS_DB_NUM'], # Use the configured DB number for app data
        password=os.environ.get('REDIS_PASSWORD', None),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True, # Good for stability
        retry_on_timeout=True  # Optional, good for resilience
    )
    redis_client.ping()
    app.logger.info(f"Flask app successfully connected to Redis DB {app.config['APP_REDIS_DB_NUM']}.")
except Exception as e:
    app.logger.error(f"FATAL: Flask app could not connect to Redis DB {app.config['APP_REDIS_DB_NUM']}: {e}. Application may not function correctly.")
    redis_client = None

# --- Jinja Filters ---
def timestamp_to_date_filter(timestamp_str):
    if not timestamp_str: return "N/A"
    try:
        ts = float(timestamp_str)
        dt_object = datetime.datetime.fromtimestamp(ts)
        return dt_object.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError) as e:
        app.logger.debug(f"Error converting timestamp '{timestamp_str}': {e}")
        return "Invalid Date"
app.jinja_env.filters['timestamp_to_date'] = timestamp_to_date_filter

# --- Allowed File Extensions & MIME Types ---
ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'svg', 'avif', 'bmp', 'ico',
    'mp4', 'mkv', 'mov', 'webm', 'ogv', '3gp', '3g2', 'avi', 'wmv', 'flv', 'mpg', 'mpeg',
    'mp3', 'aac', 'wav', 'ogg', 'opus', 'flac', 'm4a', 'wma',
    'pdf'
}
MIME_TYPE_MAP = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.gif': 'image/gif', '.webp': 'image/webp', '.heic': 'image/heic',
    '.heif': 'image/heif', '.svg': 'image/svg+xml', '.avif': 'image/avif',
    '.bmp': 'image/bmp', '.ico': 'image/x-icon',
    '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.mkv': 'video/x-matroska',
    '.webm': 'video/webm', '.ogv': 'video/ogg', '.3gp': 'video/3gpp', '.3g2': 'video/3gpp2',
    '.avi': 'video/x-msvideo', '.wmv': 'video/x-ms-wmv', '.flv': 'video/x-flv',
    '.mpg': 'video/mpeg', '.mpeg': 'video/mpeg',
    '.mp3': 'audio/mpeg', '.aac': 'audio/aac', '.wav': 'audio/wav',
    '.ogg': 'audio/ogg', '.opus': 'audio/opus', '.flac': 'audio/flac',
    '.m4a': 'audio/mp4', '.wma': 'audio/x-ms-wma',
    '.pdf': 'application/pdf'
}

def allowed_file(filename):
    if not filename or '.' not in filename: return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Helper function to get Redis client for app data within Celery tasks ---
def get_app_data_redis_client():
    return redis.Redis(
        host=current_app.config.get('REDIS_HOST', os.environ.get('REDIS_HOST', 'localhost')),
        port=int(current_app.config.get('REDIS_PORT', os.environ.get('REDIS_PORT', 6379))),
        db=current_app.config.get('APP_REDIS_DB_NUM', 0), # Use the app's data DB
        password=current_app.config.get('REDIS_PASSWORD', os.environ.get('REDIS_PASSWORD', None)),
        decode_responses=True, socket_connect_timeout=5
    )

# --- Initial Admin User Setup ---
if redis_client:
    try:
        if not redis_client.sismember('users', 'admin'):
            admin_password = os.environ.get('LIGHTBOX_ADMIN_PASSWORD', 'ChangeThisDefaultAdminPassw0rd!')
            if admin_password == 'ChangeThisDefaultAdminPassw0rd!':
                 app.logger.warning("SECURITY WARNING: Using default admin password. SET LIGHTBOX_ADMIN_PASSWORD ENV VAR for production.")
            redis_client.sadd('users', 'admin')
            redis_client.hset('user:admin', mapping={'password_hash': generate_password_hash(admin_password), 'is_admin': '1'})
            app.logger.info("Admin user 'admin' created/verified.")
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error during admin user setup: {e}")
else: app.logger.warning("Redis not connected. Admin user setup skipped.")

# --- Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page.', 'warning'); return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session: flash('Please log in.', 'warning'); return redirect(url_for('login', next=request.url))
        if not session.get('is_admin'): flash('Admin privileges required.', 'danger'); return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def owner_or_admin_access_required(item_type='batch'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session: flash('Please log in.', 'warning'); return redirect(url_for('login', next=request.url))
            if not redis_client: abort(503, description="Database service temporarily unavailable.")
            item_id_key_in_kwargs = f'{item_type}_id'
            item_id_to_check = kwargs.get(item_id_key_in_kwargs)
            if not item_id_to_check:
                app.logger.error(f"Ownership check failed: No ID for '{item_type}'. Kwargs: {kwargs}")
                flash('Cannot verify ownership: Item ID missing.', 'danger'); return redirect(url_for('index'))
            item_id_to_check_str = str(item_id_to_check)
            item_data_key = f'{item_type}:{item_id_to_check_str}'
            try: item_data = redis_client.hgetall(item_data_key)
            except redis.exceptions.RedisError as e:
                app.logger.error(f"Redis error fetching '{item_data_key}' for ownership check: {e}")
                abort(503, description="Database error during ownership check.")
            if not item_data: flash(f'{item_type.capitalize()} not found.', 'warning'); return redirect(url_for('index'))
            owner_field_in_redis = 'uploader_user_id' if item_type == 'media' else 'user_id'
            item_owner_username = item_data.get(owner_field_in_redis)
            if not item_owner_username:
                app.logger.error(f"Ownership check failed: Owner field '{owner_field_in_redis}' missing for {item_data_key}.")
                flash('Cannot verify ownership: Item data inconsistent.', 'danger'); return redirect(url_for('index'))
            if item_owner_username != session['username'] and not session.get('is_admin'):
                flash(f'You do not have permission to access this {item_type}.', 'danger'); return redirect(url_for('index'))
            item_data['id_str_for_template'] = item_id_to_check_str
            kwargs[f'{item_type}_data'] = item_data
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Celery Task for Video Conversion ---
@celery.task(bind=True, name='app.convert_video_to_mp4_task', max_retries=3, default_retry_delay=120)
def convert_video_to_mp4_task(self, original_video_temp_path, target_mp4_disk_path,
                               media_id_for_update, batch_id_for_update,
                               original_filename_for_log, disk_path_segment_for_batch,
                               uploader_username_for_log):
    task_id = self.request.id; logger = current_app.logger
    logger.info(f"[VideoTask {task_id}] User:{uploader_username_for_log} Starting Video->MP4: {original_filename_for_log} (MediaID:{media_id_for_update})")
    ffmpeg_path = current_app.config.get('FFMPEG_PATH', 'ffmpeg')
    logger.info(f"[VideoTask {task_id}] Using FFmpeg: {ffmpeg_path}")

    vid_codec = current_app.config.get('VIDEO_MP4_VIDEO_CODEC'); vid_preset = current_app.config.get('VIDEO_MP4_VIDEO_PRESET')
    vid_crf = current_app.config.get('VIDEO_MP4_VIDEO_CRF'); aud_codec = current_app.config.get('VIDEO_MP4_AUDIO_CODEC')
    aud_bitrate = current_app.config.get('VIDEO_MP4_AUDIO_BITRATE')

    ffmpeg_command = [
        ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-i', original_video_temp_path,
        '-c:v', vid_codec, '-preset', vid_preset, '-crf', vid_crf,
        '-c:a', aud_codec, '-b:a', aud_bitrate,
        '-movflags', '+faststart', '-f', 'mp4', '-y', target_mp4_disk_path
    ]
    processing_status_update = {'processing_status': 'failed', 'error_message': 'Unknown video conversion error.'}
    try:
        logger.info(f"[VideoTask {task_id}] Executing FFmpeg (Video->MP4): {' '.join(ffmpeg_command)}")
        process = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, timeout=10800) # 3hr timeout
        logger.info(f"[VideoTask {task_id}] FFmpeg Video->MP4 success: {original_filename_for_log}")
        final_output_filename = os.path.basename(target_mp4_disk_path)
        final_redis_filepath = os.path.join(disk_path_segment_for_batch, final_output_filename)
        processing_status_update = {
            'filename_on_disk': final_output_filename, 'filepath': final_redis_filepath,
            'mimetype': 'video/mp4', 'processing_status': 'completed', 'error_message': ''
        }
        task_app_data_redis_client = get_app_data_redis_client() # Use helper for correct DB
        task_app_data_redis_client.hmset(f'media:{media_id_for_update}', processing_status_update)
        logger.info(f"[VideoTask {task_id}] AppData Redis DB updated for Video MediaID {media_id_for_update}.")
        return {'status': 'success', 'output_path': target_mp4_disk_path, 'media_id': media_id_for_update}
    except subprocess.CalledProcessError as e_ffmpeg:
        error_output = e_ffmpeg.stderr.strip() if e_ffmpeg.stderr else "No stderr output from FFmpeg."
        logger.error(f"[VideoTask {task_id}] FFmpeg VIDEO->MP4 FAILED (rc {e_ffmpeg.returncode}): {original_filename_for_log}. FFmpeg Error: {error_output}")
        processing_status_update.update({'error_message': f'Video conv. error (rc {e_ffmpeg.returncode}): {error_output[:200]}'})
        if self.request.retries < self.max_retries: # Note: Celery 5.x uses self.request.retries
            logger.info(f"[VideoTask {task_id}] Retrying FAILED VIDEO task ({self.request.retries + 1}/{self.max_retries})..."); raise self.retry(exc=e_ffmpeg, countdown=int(self.default_retry_delay * (2 ** self.request.retries))) # Exponential backoff
        raise
    except subprocess.TimeoutExpired as e_timeout:
        logger.error(f"[VideoTask {task_id}] FFmpeg VIDEO->MP4 TIMEOUT: {original_filename_for_log}")
        processing_status_update.update({'error_message': 'Video conversion timeout.'})
        if self.request.retries < self.max_retries:
            logger.info(f"[VideoTask {task_id}] Retrying TIMEOUT VIDEO task ({self.request.retries + 1}/{self.max_retries})..."); raise self.retry(exc=e_timeout, countdown=int(self.default_retry_delay * (2 ** self.request.retries)))
        raise
    except Exception as e:
        logger.error(f"[VideoTask {task_id}] Unexpected error during VIDEO->MP4: {e}", exc_info=True)
        processing_status_update.update({'error_message': f'Unexpected video conv. error: {str(e)[:100]}'}); raise
    finally:
        final_update_app_data_redis_client = get_app_data_redis_client() # Use helper
        try:
            current_media_status_in_app_db = final_update_app_data_redis_client.hget(f'media:{media_id_for_update}', 'processing_status')
            if 'processing_status' in processing_status_update and current_media_status_in_app_db != 'completed':
                 final_update_app_data_redis_client.hmset(f'media:{media_id_for_update}', processing_status_update)
            logger.info(f"[VideoTask {task_id}] Final AppData Redis DB status for Video MediaID {media_id_for_update}: {processing_status_update.get('processing_status', 'NOT_SET_IN_FINALLY')}")
        except Exception as redis_e_final:
            logger.error(f"[VideoTask {task_id}] CRITICAL: Failed AppData Redis DB update in finally for Video MediaID {media_id_for_update}: {redis_e_final}")
        if os.path.exists(original_video_temp_path): # Cleanup original temp input
            try: os.remove(original_video_temp_path); logger.info(f"[VideoTask {task_id}] Cleaned temp video file: {original_video_temp_path}")
            except OSError as e_rm: logger.error(f"[VideoTask {task_id}] Error removing temp video file {original_video_temp_path}: {e_rm}")

# --- Celery Task for Audio Conversion to MP3 ---
@celery.task(bind=True, name='app.transcode_audio_to_mp3_task', max_retries=3, default_retry_delay=60)
def transcode_audio_to_mp3_task(self, original_audio_temp_path, target_mp3_disk_path,
                                media_id_for_update, batch_id_for_update,
                                original_filename_for_log, disk_path_segment_for_batch,
                                uploader_username_for_log):
    task_id = self.request.id; logger = current_app.logger
    logger.info(f"[AudioTask {task_id}] User:{uploader_username_for_log} Starting Audio->MP3: {original_filename_for_log} (MediaID:{media_id_for_update})")
    ffmpeg_path = current_app.config.get('FFMPEG_PATH', 'ffmpeg')
    logger.info(f"[AudioTask {task_id}] Using FFmpeg: {ffmpeg_path}")

    mp3_encoder = current_app.config.get('AUDIO_MP3_ENCODER'); mp3_options = current_app.config.get('AUDIO_MP3_OPTIONS')
    mp3_sample_rate = current_app.config.get('AUDIO_MP3_SAMPLE_RATE')

    ffmpeg_command = [ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-i', original_audio_temp_path, '-c:a', mp3_encoder]
    ffmpeg_command.extend(mp3_options)
    if mp3_sample_rate: ffmpeg_command.extend(['-ar', mp3_sample_rate])
    ffmpeg_command.extend(['-f', 'mp3', '-y', target_mp3_disk_path])

    processing_status_update = {'processing_status': 'failed', 'error_message': 'Unknown audio to MP3 error.'}
    try:
        logger.info(f"[AudioTask {task_id}] Executing FFmpeg (Audio->MP3): {' '.join(ffmpeg_command)}")
        process = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, timeout=3600) # 1hr timeout
        logger.info(f"[AudioTask {task_id}] FFmpeg Audio->MP3 success: {original_filename_for_log}")
        final_output_filename = os.path.basename(target_mp3_disk_path)
        final_redis_filepath = os.path.join(disk_path_segment_for_batch, final_output_filename)
        processing_status_update = {
            'filename_on_disk': final_output_filename, 'filepath': final_redis_filepath,
            'mimetype': 'audio/mpeg', 'processing_status': 'completed', 'error_message': ''
        }
        task_app_data_redis_client = get_app_data_redis_client() # Use helper for correct DB
        task_app_data_redis_client.hmset(f'media:{media_id_for_update}', processing_status_update)
        logger.info(f"[AudioTask {task_id}] AppData Redis DB updated for Audio MediaID {media_id_for_update}.")
        return {'status': 'success', 'output_path': target_mp3_disk_path, 'media_id': media_id_for_update}
    except subprocess.CalledProcessError as e_ffmpeg:
        error_output = e_ffmpeg.stderr.strip() if e_ffmpeg.stderr else "No stderr output from FFmpeg."
        logger.error(f"[AudioTask {task_id}] FFmpeg AUDIO->MP3 FAILED (rc {e_ffmpeg.returncode}): {original_filename_for_log}. FFmpeg Error: {error_output}")
        processing_status_update.update({'error_message': f'Audio conv. error (rc {e_ffmpeg.returncode}): {error_output[:200]}'})
        if self.request.retries < self.max_retries:
            logger.info(f"[AudioTask {task_id}] Retrying FAILED AUDIO task ({self.request.retries + 1}/{self.max_retries})..."); raise self.retry(exc=e_ffmpeg, countdown=int(self.default_retry_delay * (2 ** self.request.retries)))
        raise
    except subprocess.TimeoutExpired as e_timeout:
        logger.error(f"[AudioTask {task_id}] FFmpeg AUDIO->MP3 TIMEOUT: {original_filename_for_log}")
        processing_status_update.update({'error_message': 'Audio conversion timeout.'})
        if self.request.retries < self.max_retries:
            logger.info(f"[AudioTask {task_id}] Retrying TIMEOUT AUDIO task ({self.request.retries + 1}/{self.max_retries})..."); raise self.retry(exc=e_timeout, countdown=int(self.default_retry_delay * (2 ** self.request.retries)))
        raise
    except Exception as e:
        logger.error(f"[AudioTask {task_id}] Unexpected error during AUDIO->MP3: {e}", exc_info=True)
        processing_status_update.update({'error_message': f'Unexpected audio conv. error: {str(e)[:100]}'}); raise
    finally:
        final_update_app_data_redis_client = get_app_data_redis_client() # Use helper
        try:
            current_media_status_in_app_db = final_update_app_data_redis_client.hget(f'media:{media_id_for_update}', 'processing_status')
            if 'processing_status' in processing_status_update and current_media_status_in_app_db != 'completed':
                 final_update_app_data_redis_client.hmset(f'media:{media_id_for_update}', processing_status_update)
            logger.info(f"[AudioTask {task_id}] Final AppData Redis DB status for Audio MediaID {media_id_for_update}: {processing_status_update.get('processing_status', 'NOT_SET_IN_FINALLY')}")
        except Exception as redis_e_final:
            logger.error(f"[AudioTask {task_id}] CRITICAL: Failed AppData Redis DB update in finally for Audio MediaID {media_id_for_update}: {redis_e_final}")
        # --- TEMP FILE CLEANUP: os.remove() IS STILL COMMENTED OUT FOR DEBUGGING ---
        if os.path.exists(original_audio_temp_path):
            # os.remove(original_audio_temp_path) # <<< DEBUG: This line REMAINS COMMENTED OUT for initial testing.
            logger.info(f"[AudioTask {task_id}] DEBUG: Cleanup of temp audio file SKIPPED (os.remove commented out): {original_audio_temp_path}")
        else:
            logger.warning(f"[AudioTask {task_id}] DEBUG: Temp audio file NOT found at end of task (cannot remove): {original_audio_temp_path}")


# --- Routes ---
@app.route('/')
@app.route('/index')
@login_required
def index():
    if not redis_client:
        flash('Database service unavailable. Please try again later.', 'danger')
        return render_template('index.html', batches=[], upload_form_hint="Media uploads temporarily unavailable.")
    username = session['username']
    try:
        batch_ids = redis_client.lrange(f'user:{username}:batches', 0, -1)
        batches_data = []
        for batch_id in batch_ids:
            batch_info = redis_client.hgetall(f'batch:{batch_id}')
            if batch_info:
                batch_info['id'] = batch_id
                completed_media_count = 0
                media_ids_in_batch = redis_client.lrange(f'batch:{batch_id}:media_ids', 0, -1)
                for mid in media_ids_in_batch:
                    m_status = redis_client.hget(f'media:{mid}', 'processing_status')
                    if m_status == 'completed' or m_status is None: # is None for legacy items
                        completed_media_count += 1
                batch_info['item_count'] = completed_media_count
                batches_data.append(batch_info)
        batches_data.sort(key=lambda x: float(x.get('creation_timestamp', 0)), reverse=True)
        upload_form_hint = "Allowed: Images, Videos, Audio, PDF. Videos convert to MP4. Most other audio converts to high-quality MP3."
        return render_template('index.html', batches=batches_data, upload_form_hint=upload_form_hint)
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error for user {username} on index: {e}")
        flash('Error retrieving your lightboxes. Please try again.', 'danger')
        return render_template('index.html', batches=[], upload_form_hint="Error loading data.")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('username'): return redirect(url_for('index')) # If already logged in
    if request.method == 'POST':
        if not redis_client: flash('Registration service temporarily unavailable.', 'danger'); return render_template('register.html')
        username = request.form.get('username','').strip()
        password = request.form.get('password'); confirm_password = request.form.get('confirm_password')
        if not all([username, password, confirm_password]): flash('All fields are required.', 'danger'); return render_template('register.html')
        if len(username) < 3: flash('Username must be at least 3 characters long.', 'danger'); return render_template('register.html')
        if password != confirm_password: flash('Passwords do not match.', 'danger'); return render_template('register.html')
        if len(password) < 8: flash('Password must be at least 8 characters long.', 'danger'); return render_template('register.html') # Slightly stronger
        try:
            if redis_client.sismember('users', username): flash('Username already exists.', 'danger'); return render_template('register.html')
            pipe = redis_client.pipeline()
            pipe.sadd('users', username)
            pipe.hset(f'user:{username}', mapping={'password_hash': generate_password_hash(password), 'is_admin': '0'})
            pipe.execute()
            app.logger.info(f"New user registered: {username}")
            flash('Registration successful! You can now log in.', 'success'); return redirect(url_for('login'))
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error during registration for {username}: {e}"); flash('An error occurred during registration. Please try again.', 'danger')
    return render_template('register.html')

@app.route('/about') # Should be accessible without login
def about_page():
    # TODO: Update templates/about.html to reflect new audio (MP3) and video (MP4) conversion strategies.
    return render_template('about.html')

@app.route('/ross-nesbitt') # Or any URL path you prefer, e.g., /developer, /meet-ross
def ross_nesbitt_profile():
    return render_template('rossnesbitt.html')

@app.route('/why-lightbox') # Or /value, /save-money, /our-mission etc.
def why_lightbox_page():
    return render_template('why.html') # Or whatever you named your HTML file

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('username'): return redirect(url_for('index')) # If already logged in
    if request.method == 'POST':
        if not redis_client: flash('Login service temporarily unavailable.', 'danger'); return render_template('login.html')
        username = request.form.get('username'); password = request.form.get('password')
        try:
            if not redis_client.sismember('users', username): flash('Invalid username or password.', 'danger'); return render_template('login.html')
            user_data = redis_client.hgetall(f'user:{username}')
            if not user_data or not check_password_hash(user_data.get('password_hash',''), password): # Check for empty hash too
                flash('Invalid username or password.', 'danger'); return render_template('login.html')
            session['username'] = username; session['is_admin'] = user_data.get('is_admin') == '1'; session.permanent = True
            app.logger.info(f"User '{username}' logged in successfully.")
            flash(f'Welcome back, {username}!', 'success')
            next_url = request.args.get('next')
            if next_url and url_parse(next_url).netloc == '' and url_parse(next_url).scheme == '': # Basic check for local redirect
                return redirect(next_url)
            return redirect(url_for('index'))
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error during login for {username}: {e}"); flash('An error occurred during login. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    username = session.pop('username', 'UnknownUser') # Get username before clearing for log
    session.clear()
    app.logger.info(f"User '{username}' logged out.")
    flash('You have been successfully logged out.', 'info'); return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if not redis_client: flash('DB service unavailable. Upload failed.', 'danger'); return redirect(request.referrer or url_for('index'))
    if 'files[]' not in request.files: flash('No file part in form.', 'danger'); return redirect(request.referrer or url_for('index'))
    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files): flash('No files selected.', 'danger'); return redirect(request.referrer or url_for('index'))

    current_user_username = session['username']
    existing_batch_id = request.form.get('existing_batch_id')
    batch_id_to_use, batch_name_to_use, is_new_batch, batch_owner_username = "", "", True, current_user_username

    if existing_batch_id: # Adding to existing batch
        is_new_batch = False; batch_id_to_use = existing_batch_id
        try:
            batch_info = redis_client.hgetall(f'batch:{batch_id_to_use}')
            if not batch_info: flash(f'Selected batch (ID: {batch_id_to_use}) not found.', 'danger'); return redirect(request.referrer or url_for('index'))
            batch_owner_username = batch_info.get('user_id')
            if not batch_owner_username: app.logger.error(f"Batch {batch_id_to_use} is missing 'user_id'."); flash('Selected batch data inconsistent.', 'danger'); return redirect(request.referrer or url_for('index'))
            if batch_owner_username != current_user_username and not session.get('is_admin'): flash('You do not have permission to add files to this batch.', 'danger'); return redirect(request.referrer or url_for('index'))
            batch_name_to_use = batch_info.get('name', f'Batch_{batch_id_to_use[:8]}')
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error checking batch {batch_id_to_use}: {e}"); flash("Database error verifying batch.", "danger"); return redirect(request.referrer or url_for('index'))
    else: # Creating new batch
        is_new_batch = True; batch_name_from_form = request.form.get('batch_name', '').strip()
        if not batch_name_from_form: flash('A name is required for a new batch.', 'warning'); return redirect(request.referrer or url_for('index'))
        batch_id_to_use = str(uuid.uuid4()); batch_name_to_use = batch_name_from_form
    
    disk_path_segment_for_batch = os.path.join(batch_owner_username, batch_id_to_use)
    full_disk_upload_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], disk_path_segment_for_batch)
    try: os.makedirs(full_disk_upload_dir, exist_ok=True)
    except OSError as e: app.logger.error(f"Error creating upload directory '{full_disk_upload_dir}': {e}"); flash("Server error creating upload directory.", "danger"); return redirect(request.referrer or url_for('index'))

    files_uploaded_count = 0; files_queued_count = 0
    redis_pipe = redis_client.pipeline()
    
    video_formats_to_convert = app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4']
    audio_formats_to_convert = app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3']

    def get_unique_disk_path(directory, base_name, extension_with_dot): # Ensure leading dot in extension
        counter = 0; filename = f"{base_name}{extension_with_dot}"
        path = os.path.join(directory, filename)
        _base = base_name
        while os.path.exists(path):
            counter += 1; filename = f"{_base}_{counter}{extension_with_dot}"; path = os.path.join(directory, filename)
        return path, filename

    for file_item in files:
        if not file_item or not file_item.filename: continue # Skip empty file parts
        original_filename = file_item.filename

        if not allowed_file(original_filename):
            if original_filename: flash(f'File type of "{original_filename}" not allowed. Skipped.', 'warning')
            continue

        base_name, ext_with_dot = os.path.splitext(original_filename); ext_with_dot = ext_with_dot.lower()
        ext_lower_no_dot = ext_with_dot.lstrip('.')
        media_id = str(uuid.uuid4())
        secure_base_name = secure_filename(base_name) if base_name else f"media_{media_id[:8]}" # Ensure secure_base has a value
        
        # Path for temporarily saving the uploaded file before processing or final move
        temp_input_on_disk_filename = f"{media_id}_celery_input.{ext_lower_no_dot}" # Use original ext for temp file
        temp_input_on_disk_path = os.path.join(full_disk_upload_dir, temp_input_on_disk_filename)
        
        # This is the path that will be stored in Redis if file is queued (path to temp file)
        # OR path to final file if directly saved (after move/rename)
        initial_redis_filepath_for_queued = os.path.join(disk_path_segment_for_batch, temp_input_on_disk_filename)

        common_media_data = {
            'original_filename': original_filename, 'filename_on_disk': "", # Will be set below
            'filepath': "", # Will be set below
            'mimetype': MIME_TYPE_MAP.get(ext_with_dot, 'application/octet-stream'),
            'is_hidden': '0', 'is_liked': '0', 'uploader_user_id': current_user_username,
            'batch_id': batch_id_to_use, 'upload_timestamp': datetime.datetime.now().timestamp()
        }

        try:
            if ext_lower_no_dot in video_formats_to_convert:
                app.logger.info(f"Queuing Video '{original_filename}' for MP4 conversion. MediaID: {media_id}")
                file_item.save(temp_input_on_disk_path) # Save to temp location
                target_disk_path, _ = get_unique_disk_path(full_disk_upload_dir, secure_base_name, ".mp4")
                redis_pipe.hmset(f'media:{media_id}', {
                    **common_media_data, 
                    'filename_on_disk': temp_input_on_disk_filename, # Temp input filename
                    'filepath': initial_redis_filepath_for_queued,   # Path to temp input
                    'processing_status': 'queued'
                })
                convert_video_to_mp4_task.apply_async(args=[temp_input_on_disk_path, target_disk_path, media_id, batch_id_to_use, original_filename, disk_path_segment_for_batch, current_user_username])
                files_queued_count += 1
            elif ext_lower_no_dot in audio_formats_to_convert: # e.g. WAV, FLAC, M4A, OGG etc. -> MP3
                app.logger.info(f"Queuing Audio '{original_filename}' for MP3 conversion. MediaID: {media_id}")
                file_item.save(temp_input_on_disk_path) # Save to temp location
                target_disk_path, _ = get_unique_disk_path(full_disk_upload_dir, secure_base_name, ".mp3")
                redis_pipe.hmset(f'media:{media_id}', {
                    **common_media_data,
                    'filename_on_disk': temp_input_on_disk_filename, # Temp input filename
                    'filepath': initial_redis_filepath_for_queued,   # Path to temp input
                    'processing_status': 'queued'
                })
                transcode_audio_to_mp3_task.apply_async(args=[temp_input_on_disk_path, target_disk_path, media_id, batch_id_to_use, original_filename, disk_path_segment_for_batch, current_user_username])
                files_queued_count += 1
            else: # Direct save (MP3s, Images, PDFs, etc.)
                app.logger.info(f"Directly saving '{original_filename}'. MediaID: {media_id}")
                final_disk_path, final_filename_on_server = get_unique_disk_path(full_disk_upload_dir, secure_base_name, ext_with_dot)
                file_item.save(final_disk_path) # Save directly to final path & name
                final_redis_filepath = os.path.join(disk_path_segment_for_batch, final_filename_on_server)
                redis_pipe.hmset(f'media:{media_id}', {
                    **common_media_data,
                    'filename_on_disk': final_filename_on_server, # Final filename
                    'filepath': final_redis_filepath,             # Final path
                    'processing_status': 'completed'
                })
                files_uploaded_count += 1
            redis_pipe.rpush(f'batch:{batch_id_to_use}:media_ids', media_id)
        except Exception as e_process_file:
            app.logger.error(f"Error processing file '{original_filename}' during upload: {e_process_file}", exc_info=True)
            flash(f"Error handling file '{original_filename}'. Skipped.", "danger")
            if os.path.exists(temp_input_on_disk_path): # If temp file was created before error
                try: os.remove(temp_input_on_disk_path)
                except OSError: app.logger.error(f"Failed to cleanup temp file during error: {temp_input_on_disk_path}")
    
    try: redis_pipe.execute() 
    except redis.exceptions.RedisError as e: 
        app.logger.error(f"Redis pipeline execution error for batch {batch_id_to_use}: {e}"); flash("Database error during upload.", "danger"); return redirect(request.referrer or url_for('index'))

    total_processed_successfully = files_uploaded_count + files_queued_count
    if total_processed_successfully > 0:
        try:
            if is_new_batch:
                redis_client.hset(f'batch:{batch_id_to_use}', mapping={
                    'user_id': batch_owner_username, 'creation_timestamp': datetime.datetime.now().timestamp(),
                    'name': batch_name_to_use, 'is_shared': '0', 'share_token': ''
                })
                redis_client.lpush(f'user:{batch_owner_username}:batches', batch_id_to_use)
            else: redis_client.hset(f'batch:{batch_id_to_use}', 'last_modified_timestamp', datetime.datetime.now().timestamp())
            
            msg_parts = [f'{total_processed_successfully} file(s) submitted for batch "{batch_name_to_use}".']
            if files_queued_count > 0: msg_parts.append("Files needing conversion are now processing.")
            flash(' '.join(msg_parts), 'success')
            return redirect(url_for('collection_view', batch_id=batch_id_to_use))
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error finalizing batch {batch_id_to_use}: {e}"); flash("Files uploaded, but error saving batch details.", "warning"); return redirect(url_for('index'))
    else:
        if is_new_batch and os.path.exists(full_disk_upload_dir) and not os.listdir(full_disk_upload_dir):
            try: shutil.rmtree(full_disk_upload_dir); app.logger.info(f"Cleaned up empty new batch directory: {full_disk_upload_dir}")
            except OSError as e_rmdir: app.logger.error(f"Error removing empty new batch directory '{full_disk_upload_dir}': {e_rmdir}")
        flash('No valid files were processed. Please check file types or selection.', 'info'); return redirect(request.referrer or url_for('index'))

# --- Batch/Media View and Action Routes ---
@app.route('/batch/<uuid:batch_id>')
@login_required
@owner_or_admin_access_required(item_type='batch')
def collection_view(batch_id, batch_data):
    if not redis_client: flash('Database service unavailable.', 'danger'); return redirect(url_for('index'))
    try:
        batch_info = batch_data; batch_id_str = str(batch_id); batch_info['id'] = batch_id_str
        batch_info['is_shared_val'] = batch_info.get('is_shared', '0')
        batch_info['share_token_val'] = batch_info.get('share_token', '')
        if batch_info.get('is_shared') == '1' and batch_info.get('share_token'):
            batch_info['public_share_url'] = url_for('public_batch_view', share_token=batch_info['share_token_val'], _external=True)
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1)
        media_list = []; valid_items_count = 0; is_any_item_processing_flag = False
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata:
                mdata['id'] = mid; current_status = mdata.get('processing_status', 'completed')
                mdata['processing_status'] = current_status; mdata['error_message'] = mdata.get('error_message', '')
                if current_status not in ['completed', 'failed']: is_any_item_processing_flag = True
                rpath = mdata.get('filepath')
                if rpath: mdata['web_path'] = url_for('static', filename=f"uploads/{rpath.lstrip('/')}")
                else:
                    mdata['web_path'] = None
                    if current_status == 'completed': app.logger.warning(f"CollView: Completed media {mid} batch {batch_id_str} missing filepath.")
                media_list.append(mdata)
                if current_status == 'completed': valid_items_count +=1
        batch_info['item_count'] = valid_items_count
        return render_template('collection.html', batch=batch_info, media_items=media_list, is_any_item_processing=is_any_item_processing_flag)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error in collection_view batch {str(batch_id)}: {e}"); flash("DB error loading batch.", 'danger'); return redirect(url_for('index'))
    except Exception as e: app.logger.error(f"Error in collection_view batch {str(batch_id)}: {e}", exc_info=True); flash("Error loading collection.", "danger"); return redirect(url_for('index'))

@app.route('/slideshow/<uuid:batch_id>')
@login_required
@owner_or_admin_access_required(item_type='batch')
def slideshow(batch_id, batch_data):
    if not redis_client: flash('DB unavailable for slideshow.', 'danger'); return redirect(url_for('collection_view', batch_id=str(batch_id)) if batch_id else url_for('index'))
    try:
        batch_info = batch_data; batch_id_str = str(batch_id); batch_info['id'] = batch_id_str
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1)
        js_media_list = []
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata and mdata.get('is_hidden', '0') == '0' and mdata.get('processing_status', 'completed') == 'completed':
                rpath = mdata.get('filepath'); mimetype = mdata.get('mimetype')
                if rpath and mimetype and mimetype.startswith(('image/', 'video/', 'audio/')):
                    web_path = url_for('static', filename=f"uploads/{rpath.lstrip('/')}")
                    js_media_list.append({'filepath': web_path, 'mimetype': mimetype, 'original_filename': mdata.get('original_filename', 'unknown_file')})
        if not js_media_list: flash("No playable items for slideshow.", "info"); return redirect(url_for('collection_view', batch_id=batch_id_str))
        return render_template('slideshow.html', batch=batch_info, media_data_json=json.dumps(js_media_list), is_public_view=False)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error slideshow batch {str(batch_id)}: {e}"); flash("DB error loading slideshow.",'danger'); return redirect(url_for('collection_view', batch_id=str(batch_id)))
    except Exception as e: app.logger.error(f"Error slideshow batch {str(batch_id)}: {e}", exc_info=True); flash("Error loading slideshow.", "danger"); return redirect(url_for('collection_view', batch_id=str(batch_id)))

@app.route('/batch/<string:batch_id>/toggle_share', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='batch')
def toggle_share_batch(batch_id, batch_data):
    if not redis_client: abort(503, description="DB unavailable for sharing.")
    batch_id_str = str(batch_id)
    try:
        current_token = batch_data.get('share_token'); is_shared_str = batch_data.get('is_shared', '0')
        new_shared_bool = not (is_shared_str == '1'); update_data = {'is_shared': '1' if new_shared_bool else '0'}
        pipe = redis_client.pipeline()
        if new_shared_bool:
            if not current_token: current_token = secrets.token_urlsafe(24); update_data['share_token'] = current_token; pipe.set(f'share_token:{current_token}', batch_id_str)
        elif current_token: pipe.delete(f'share_token:{current_token}'); update_data['share_token'] = ''
        pipe.hmset(f'batch:{batch_id_str}', update_data); pipe.execute()
        app.logger.info(f"Batch '{batch_data.get('name', batch_id_str)}' sharing: {'Public' if new_shared_bool else 'Private'}")
        if new_shared_bool and current_token:
            share_url = url_for('public_batch_view', share_token=current_token, _external=True)
            flash(f'Batch "{batch_data.get("name", "Untitled")}" now <strong>Public</strong>. Link: <a href="{share_url}" target="_blank" class="alert-link" style="word-break: break-all;">{share_url}</a>', 'success')
        else: flash(f'Batch "{batch_data.get("name", "Untitled")}" now <strong>Private</strong>. Links deactivated.', 'info')
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error toggle_share batch {batch_id_str}: {e}"); flash("DB error updating sharing.", "danger")
    except Exception as e: app.logger.error(f"Error toggle_share batch {batch_id_str}: {e}", exc_info=True); flash("Error changing sharing.", "danger")
    return redirect(url_for('collection_view', batch_id=batch_id_str))

@app.route('/public/batch/<share_token>')
def public_batch_view(share_token):
    if not redis_client: abort(503, description="DB unavailable.")
    try:
        batch_id_str = redis_client.get(f'share_token:{share_token}')
        if not batch_id_str: app.logger.warning(f"Invalid share token: {share_token}"); return render_template('public_link_invalid.html', reason="Link invalid/expired."), 404
        batch_info = redis_client.hgetall(f'batch:{batch_id_str}')
        if not batch_info or batch_info.get('is_shared', '0') != '1':
            app.logger.warning(f"Access attempt non-shared batch {batch_id_str} token {share_token}.")
            return render_template('public_link_invalid.html', reason="Batch not shared/exists."), 403
        batch_info['id'] = batch_id_str; batch_info['share_token'] = share_token
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1); media_list = []; valid_items = 0
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata and mdata.get('is_hidden', '0') == '0' and mdata.get('processing_status', 'completed') == 'completed':
                if mdata.get('filepath'): mdata['id']=mid; mdata['web_path'] = url_for('static',filename=f"uploads/{mdata['filepath'].lstrip('/')}"); media_list.append(mdata); valid_items+=1
                elif mdata.get('processing_status')=='completed': app.logger.warning(f"PublicView: Completed media {mid} batch {batch_id_str} missing filepath.")
        batch_info['item_count'] = valid_items
        return render_template('public_view.html', batch=batch_info, media_items=media_list)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error public_batch_view token {share_token}: {e}"); return render_template('public_link_invalid.html', reason="DB error."), 500
    except Exception as e: app.logger.error(f"Error public_batch_view token {share_token}: {e}", exc_info=True); return render_template('public_link_invalid.html', reason="Unexpected error."), 500

@app.route('/public/slideshow/<share_token>')
def public_slideshow_view(share_token):
    if not redis_client: abort(503, description="DB unavailable.")
    try:
        batch_id_str = redis_client.get(f'share_token:{share_token}')
        if not batch_id_str: return render_template('public_link_invalid.html', reason="Invalid slideshow link."), 404
        batch_info = redis_client.hgetall(f'batch:{batch_id_str}')
        if not batch_info or batch_info.get('is_shared', '0') != '1': return render_template('public_link_invalid.html', reason="Slideshow not shared."), 403
        batch_info['id'] = batch_id_str; batch_info['share_token'] = share_token
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1); js_media_list = []
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata and mdata.get('is_hidden','0')=='0' and mdata.get('processing_status','completed')=='completed':
                rpath = mdata.get('filepath'); mimetype = mdata.get('mimetype')
                if rpath and mimetype and mimetype.startswith(('image/','video/','audio/')):
                    js_media_list.append({'filepath':url_for('static',filename=f"uploads/{rpath.lstrip('/')}"),'mimetype':mimetype,'original_filename':mdata.get('original_filename','unknown')})
        if not js_media_list: flash("No playable items in shared slideshow.", "info"); return redirect(url_for('public_batch_view', share_token=share_token))
        return render_template('slideshow.html', batch=batch_info, media_data_json=json.dumps(js_media_list), is_public_view=True)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error public_slideshow token {share_token}: {e}"); return render_template('public_link_invalid.html', reason="DB error slideshow."), 500
    except Exception as e: app.logger.error(f"Error public_slideshow token {share_token}: {e}", exc_info=True); return render_template('public_link_invalid.html', reason="Error slideshow."), 500

@app.route('/media/<uuid:media_id>/toggle_hidden', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media')
def toggle_hidden(media_id, media_data):
    if not redis_client: abort(503, description="DB unavailable.")
    media_id_str = str(media_id)
    try:
        new_status = '0' if media_data.get('is_hidden', '0') == '1' else '1'
        redis_client.hset(f'media:{media_id_str}', 'is_hidden', new_status)
        flash(f"Media '{media_data.get('original_filename', media_id_str)}' now {'visible' if new_status == '0' else 'hidden'}.", 'success')
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error toggle_hidden media {media_id_str}: {e}"); flash("DB error visibility.", "danger")
    except Exception as e: app.logger.error(f"Error toggle_hidden media {media_id_str}: {e}", exc_info=True); flash("Error visibility.", "danger")
    return redirect(url_for('collection_view', batch_id=media_data.get('batch_id')) if media_data.get('batch_id') else request.referrer or url_for('index') )

@app.route('/media/<uuid:media_id>/toggle_liked', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media')
def toggle_liked(media_id, media_data):
    if not redis_client: abort(503, description="DB unavailable.")
    media_id_str = str(media_id)
    try:
        new_status = '0' if media_data.get('is_liked', '0') == '1' else '1'
        redis_client.hset(f'media:{media_id_str}', 'is_liked', new_status)
        flash(f"Media '{media_data.get('original_filename', media_id_str)}' {'unliked' if new_status == '0' else 'liked'}.", 'success')
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error toggle_liked media {media_id_str}: {e}"); flash("DB error like status.", "danger")
    except Exception as e: app.logger.error(f"Error toggle_liked media {media_id_str}: {e}", exc_info=True); flash("Error like status.", "danger")
    return redirect(url_for('collection_view', batch_id=media_data.get('batch_id')) if media_data.get('batch_id') else request.referrer or url_for('index'))

@app.route('/media/<uuid:media_id>/delete', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media')
def delete_media(media_id, media_data):
    if not redis_client: abort(503, description="DB unavailable.")
    media_id_str = str(media_id); batch_id_redirect = media_data.get('batch_id'); orig_filename = media_data.get('original_filename', media_id_str)
    try:
        filepath_redis = media_data.get('filepath')
        if filepath_redis:
            disk_path_del = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filepath_redis)
            if os.path.isfile(disk_path_del):
                try: os.remove(disk_path_del); app.logger.info(f"Deleted file {disk_path_del} for media {media_id_str}")
                except OSError as e: app.logger.error(f"OS error deleting {disk_path_del} for media {media_id_str}: {e}")
            elif os.path.exists(disk_path_del): app.logger.warning(f"Path {disk_path_del} not a file, media {media_id_str}")
            else: app.logger.info(f"File {disk_path_del} for media {media_id_str} (status: {media_data.get('processing_status')}) not found on disk for deletion (might have been cleaned up).")
        else: app.logger.warning(f"No filepath in Redis for media {media_id_str}.")
        pipe = redis_client.pipeline()
        if batch_id_redirect: pipe.lrem(f'batch:{batch_id_redirect}:media_ids', 0, media_id_str)
        pipe.delete(f'media:{media_id_str}'); pipe.execute()
        flash(f"Media item '{orig_filename}' deleted.", 'success')
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error deleting media {media_id_str}: {e}"); flash("DB error deleting media.", "danger")
    except Exception as e: app.logger.error(f"Error deleting media {media_id_str}: {e}", exc_info=True); flash("Error deleting media.", "danger")
    if batch_id_redirect: return redirect(url_for('collection_view', batch_id=batch_id_redirect))
    return redirect(url_for('index'))

@app.route('/batch/<uuid:batch_id>/delete', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='batch')
def delete_batch(batch_id, batch_data):
    if not redis_client: abort(503, description="DB unavailable.")
    batch_id_str = str(batch_id); batch_name_flash = batch_data.get('name', batch_id_str); user_id_owner = batch_data.get('user_id')
    try:
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1)
        pipe = redis_client.pipeline()
        if media_ids: # Delete all associated media items from Redis (files deleted with folder)
            for m_id in media_ids: pipe.delete(f'media:{m_id}')
        pipe.delete(f'batch:{batch_id_str}:media_ids'); pipe.delete(f'batch:{batch_id_str}')
        if batch_data.get('share_token'): pipe.delete(f"share_token:{batch_data['share_token']}")
        if user_id_owner: pipe.lrem(f'user:{user_id_owner}:batches', 0, batch_id_str)
        pipe.execute()
        app.logger.info(f"Batch {batch_id_str} metadata deleted from Redis.")
        if user_id_owner: # Delete folder from disk
            batch_dir_disk = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], user_id_owner, batch_id_str)
            if os.path.isdir(batch_dir_disk): # Check if it's a directory before rmtree
                try: shutil.rmtree(batch_dir_disk); app.logger.info(f"Deleted batch directory: {batch_dir_disk}")
                except OSError as e: app.logger.error(f"OS error deleting dir {batch_dir_disk}: {e}"); flash("Error deleting batch files.", "warning")
            else: app.logger.info(f"Batch dir not found for deletion: {batch_dir_disk}")
        else: app.logger.error(f"Cannot delete batch dir for {batch_id_str}: user_id missing."); flash("Could not delete files: owner unknown.", "warning")
        flash(f'Batch "{batch_name_flash}" deleted.', 'success'); return redirect(url_for('index'))
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error deleting batch {batch_id_str}: {e}"); flash("DB error deleting batch.", "danger")
    except Exception as e: app.logger.error(f"Error deleting batch {batch_id_str}: {e}", exc_info=True); flash("Error deleting batch.", "danger")
    return redirect(url_for('index'))

@app.route('/batch/<uuid:batch_id>/export')
@login_required
@owner_or_admin_access_required(item_type='batch')
def export_batch(batch_id, batch_data):
    if not redis_client: abort(503, description="DB unavailable.")
    batch_id_str = str(batch_id)
    try:
        memory_zip = BytesIO(); files_added = 0
        safe_batch_name = secure_filename(batch_data.get('name', f'batch_{batch_id_str[:8]}')).replace(' ', '_')
        with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1)
            if not media_ids: flash("Batch empty, nothing to export.", "info"); return redirect(url_for('collection_view', batch_id=batch_id_str))
            for mid in media_ids:
                minfo = redis_client.hgetall(f'media:{mid}')
                if minfo and minfo.get('is_hidden','0')=='0' and minfo.get('processing_status','completed')=='completed':
                    rpath = minfo.get('filepath')
                    if rpath:
                        disk_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], rpath)
                        if os.path.isfile(disk_path):
                            arc_name = minfo.get('original_filename', os.path.basename(rpath)).replace('/','_').replace('\\','_').strip()
                            if not arc_name: arc_name = f"media_{mid}"
                            zf.write(disk_path, arcname=arc_name); files_added +=1
                        else: app.logger.warning(f"Export: File for media {mid} missing: {disk_path}")
                    else: app.logger.warning(f"Export: Filepath missing for completed media {mid}")
            if files_added == 0: flash("No exportable files found.", "warning"); return redirect(url_for('collection_view', batch_id=batch_id_str))
        memory_zip.seek(0)
        zip_filename = f"LightBox_{safe_batch_name}_Export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        app.logger.info(f"User '{session['username']}' exporting {files_added} files from batch '{batch_id_str}'.")
        return send_file(memory_zip, mimetype='application/zip', as_attachment=True, download_name=zip_filename)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error export batch {batch_id_str}: {e}"); flash("DB error during export.", "danger")
    except Exception as e: app.logger.error(f"Error export batch {batch_id_str}: {e}", exc_info=True); flash("Error during export.", "danger")
    return redirect(url_for('collection_view', batch_id=batch_id_str))

@app.route('/batch/<string:batch_id>/rename', methods=['POST'])
@login_required
# @owner_or_admin_access_required is implicitly handled by internal check
def rename_batch(batch_id):
    if not redis_client: return jsonify({'success': False, 'message': 'Database service unavailable.'}), 503
    batch_id_str = str(batch_id)
    try: batch_data = redis_client.hgetall(f'batch:{batch_id_str}')
    except redis.exceptions.RedisError as e:
        current_app.logger.error(f"Redis error fetching batch {batch_id_str} for rename: {e}")
        return jsonify({'success': False, 'message': 'Database error.'}), 500
    if not batch_data: return jsonify({'success': False, 'message': 'Batch not found.'}), 404
    owner_username = batch_data.get('user_id')
    if not owner_username: return jsonify({'success': False, 'message': 'Batch data inconsistent.'}), 500
    if owner_username != session.get('username') and not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    new_name = request.form.get('new_name', '').strip()
    if not new_name: return jsonify({'success': False, 'message': 'New name cannot be empty.'}), 400
    MAX_BATCH_NAME_LENGTH = 255
    if len(new_name) > MAX_BATCH_NAME_LENGTH: return jsonify({'success': False, 'message': f'Name cannot exceed {MAX_BATCH_NAME_LENGTH} chars.'}), 400
    old_name = batch_data.get('name', 'Unnamed Batch')
    if old_name == new_name: return jsonify({'success': True, 'message': 'Name unchanged.', 'new_name': new_name}), 200
    try:
        pipe = redis_client.pipeline()
        pipe.hset(f'batch:{batch_id_str}', 'name', new_name)
        pipe.hset(f'batch:{batch_id_str}', 'last_modified_timestamp', datetime.datetime.now().timestamp())
        pipe.execute()
        current_app.logger.info(f"Batch '{old_name}' (ID: {batch_id_str}) renamed to '{new_name}' by {session.get('username')}")
        return jsonify({'success': True, 'message': 'Batch renamed.', 'new_name': new_name}), 200
    except redis.exceptions.RedisError as e: return jsonify({'success': False, 'message': 'DB error during rename.'}), 500
    except Exception as e: current_app.logger.error(f"Error renaming batch {batch_id_str}: {e}", exc_info=True); return jsonify({'success':False,'message':'Server error rename.'}),500

# --- Admin Routes ---
@app.route('/admin/users')
@login_required
@admin_required
def admin_dashboard():
    if not redis_client: flash("Database service unavailable.", "danger"); return redirect(url_for('index'))
    try:
        all_usernames = redis_client.smembers('users')
        users_list = []
        for uname in sorted(list(all_usernames), key=lambda s: s.lower()):
            user_info = redis_client.hgetall(f'user:{uname}')
            user_info['username'] = uname # Ensure username is always in the dict
            user_info['batch_count'] = redis_client.llen(f'user:{uname}:batches')
            users_list.append(user_info)
        return render_template('admin_dashboard.html', users=users_list)
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error in admin_dashboard: {e}")
        flash("Error loading user data for admin dashboard.", "danger"); return redirect(url_for('index'))

@app.route('/admin/change_password', methods=['POST'])
@login_required
@admin_required
def change_user_password():
    if not redis_client: flash("Database service unavailable.", "danger"); return redirect(url_for('admin_dashboard'))
    target_username = request.form.get('username')
    new_password = request.form.get('new_password')
    if not target_username or not new_password:
        flash('Username and new password are required.', 'danger'); return redirect(url_for('admin_dashboard'))
    if len(new_password) < 8: # Consistent with registration
        flash('New password must be at least 8 characters long.', 'danger'); return redirect(url_for('admin_dashboard'))
    try:
        if not redis_client.sismember('users', target_username):
            flash(f'User "{target_username}" not found.', 'danger'); return redirect(url_for('admin_dashboard'))
        redis_client.hset(f'user:{target_username}', 'password_hash', generate_password_hash(new_password))
        flash(f'Password successfully updated for user "{target_username}".', 'success')
        app.logger.info(f"Admin '{session['username']}' changed password for user '{target_username}'.")
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error changing password for {target_username}: {e}")
        flash("Database error changing password.", "danger")
    return redirect(url_for('admin_dashboard'))

# -----------------------------------------------------------------------------
# ERROR HANDLERS
# -----------------------------------------------------------------------------

@app.errorhandler(400)
def bad_request_error(e):
    error_description = getattr(e, 'description', "The browser (or proxy) sent a request that this server could not understand.")
    error_title = "400 - Bad Request"
    app.logger.warning(f"HTML 400 for {request.url}: {error_description}", exc_info=e if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        app.logger.warning(f"JSON 400 for {request.url}: {error_description}")
        return jsonify(error="Bad Request", message=error_description), 400
    return render_template('400.html', error_title=error_title, error_message=error_description), 400

@app.errorhandler(401)
def unauthorized_error(e):
    error_description = getattr(e, 'description', "This server could not verify that you are authorized to access the URL requested. You either supplied the wrong credentials (e.g. a bad password), or your browser doesn't understand how to supply the credentials required.")
    error_title = "401 - Unauthorized"
    app.logger.info(f"HTML 401 for {request.url}: {error_description}") # Changed to info as it's a common flow
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        app.logger.info(f"JSON 401 for {request.url}: {error_description}")
        return jsonify(error="Unauthorized", message=error_description), 401
    return render_template('401.html', error_title=error_title, error_message=error_description), 401

@app.errorhandler(403)
def forbidden_error(e):
    error_description = getattr(e, 'description', "You don't have the permission to access the requested resource. It is either read-protected or not readable by the server.")
    error_title = "403 - Forbidden"
    app.logger.warning(f"HTML 403 for {request.url}: {error_description}", exc_info=e if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        app.logger.warning(f"JSON 403 for {request.url}: {error_description}")
        return jsonify(error="Forbidden", message=error_description), 403
    return render_template('403.html', error_title=error_title, error_message=error_description), 403

@app.errorhandler(404)
def page_not_found_error(e): # Renamed from your original to match convention
    error_description = "Page not found."
    if hasattr(e, 'description') and e.description:
        error_description = e.description
    error_title = "404 - Page Not Found"
    app.logger.warning(f"HTML 404 for {request.url}: {error_description}", exc_info=e if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        app.logger.warning(f"JSON 404 for {request.url}: {error_description}")
        return jsonify(error="Not Found", message=error_description), 404
    return render_template('404.html', error_title=error_title, error_message=error_description), 404

@app.errorhandler(413)
def request_entity_too_large_error(e): # Your existing function name was good
    max_size_bytes = app.config.get('MAX_CONTENT_LENGTH', 0)
    max_size_readable = "configured limit"
    if max_size_bytes > 0:
        gb_factor, mb_factor, kb_factor = 1024**3, 1024**2, 1024
        if max_size_bytes >= gb_factor: max_size_readable = f"{max_size_bytes / gb_factor:.1f} GB"
        elif max_size_bytes >= mb_factor: max_size_readable = f"{max_size_bytes / mb_factor:.0f} MB"
        else: max_size_readable = f"{max_size_bytes / kb_factor:.0f} KB"
    
    flash_message = f"Upload failed: File(s) too large. Maximum allowed is {max_size_readable}."
    error_title = "413 - Payload Too Large"
    
    app.logger.warning(f"413 - Request entity too large for {request.url}. {flash_message}")
    
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(error="Payload Too Large", message=flash_message, limit=max_size_readable), 413

    flash(flash_message, "danger")
    if request.referrer and request.referrer != request.url:
        return redirect(request.referrer) # Status code 413 is implied by Werkzeug for the exception

    # Fallback to rendering the 413.html page if not redirecting or JSON
    return render_template('413.html', error_title=error_title, error_message=flash_message, max_upload_size=max_size_readable), 413

@app.errorhandler(429)
def too_many_requests_error(e):
    error_description = getattr(e, 'description', "You have sent too many requests in a given amount of time.")
    error_title = "429 - Too Many Requests"
    app.logger.warning(f"HTML 429 for {request.url}: {error_description}", exc_info=e if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        app.logger.warning(f"JSON 429 for {request.url}: {error_description}")
        # Flask-Limiter often puts retry-after information in e.headers
        headers = getattr(e, 'headers', {})
        return jsonify(error="Too Many Requests", message=error_description), 429, headers
    return render_template('429.html', error_title=error_title, error_message=error_description), 429

@app.errorhandler(500)
def internal_server_error(e): # Your existing function name was good
    original_exception_str = str(getattr(e, 'original_exception', e))
    error_title = "500 - Server Error"
    error_message_for_template = "Something went wrong on our end. Please try again later or contact support if the issue persists."
    
    app.logger.error(f"500 - Internal Server Error at {request.url}: {original_exception_str}", exc_info=True)
    
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(error="Internal Server Error", message="An unexpected error occurred on the server."), 500
    return render_template('500.html', error_title=error_title, error_message=error_message_for_template), 500

@app.errorhandler(503)
def service_unavailable_error(e): # Your existing function name was good
    error_description = getattr(e, 'description', "A required service is temporarily unavailable or the server is currently unable to handle the request due to a temporary overloading or maintenance of the server.")
    error_title = "503 - Service Unavailable"
    
    app.logger.error(f"503 - Service Unavailable at {request.url}: {error_description}", exc_info=True if app.debug else False) # Maintained your exc_info logic
    
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        # Some rate limiters or proxies might add Retry-After header to the exception
        headers = getattr(e, 'headers', {})
        return jsonify(error="Service Unavailable", message=error_description), 503, headers
    return render_template('503.html', error_title=error_title, error_message=error_description), 503

# -----------------------------------------------------------------------------

# --- Main Execution ---
if __name__ == '__main__':
    print("--- Starting Flask App directly (for local development/testing only) ---")
    upload_folder_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    if not os.path.exists(upload_folder_path):
        try: os.makedirs(upload_folder_path); print(f"Created UPLOAD_FOLDER at: {upload_folder_path}")
        except OSError as e_mkdir: print(f"ERROR: Could not create UPLOAD_FOLDER at {upload_folder_path}: {e_mkdir}")

    app.logger.info(f"Flask App '{app.name}' running in '{app.env}' mode (debug={app.debug}).")
    app.logger.info(f"FFMPEG_PATH used by app: {app.config.get('FFMPEG_PATH')}")
    app.logger.info(f"APP_REDIS_DB_NUM for app data: {app.config.get('APP_REDIS_DB_NUM')}")
    app.logger.info(f"Celery Broker URL: {app.config.get('broker_url')}")
    app.logger.info(f"Celery Result Backend URL: {app.config.get('result_backend')}")
    app.logger.info(f"Video to MP4 Config: Formats='{app.config.get('VIDEO_FORMATS_TO_CONVERT_TO_MP4')}'")
    app.logger.info(f"Audio to MP3 Config: Formats='{app.config.get('AUDIO_FORMATS_TO_CONVERT_TO_MP3')}'")
    
    run_host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    run_port = int(os.environ.get('FLASK_RUN_PORT', 5102))
    
    app.run(debug=app.debug, host=run_host, port=run_port)
