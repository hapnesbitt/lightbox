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

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'fallback_dev_secret_key_ ঊ<x_bin_118> ঊ CHANGE_IN_PROD')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 9000 * 1024 * 1024
app.config['FFMPEG_PATH'] = os.environ.get('FFMPEG_PATH', 'ffmpeg')

app.config['AUDIO_MP3_ENCODER'] = 'libmp3lame'
app.config['AUDIO_MP3_OPTIONS'] = os.environ.get('AUDIO_MP3_OPTIONS', '-q:a 0 -compression_level 0').split()
app.config['AUDIO_MP3_SAMPLE_RATE'] = os.environ.get('AUDIO_MP3_SAMPLE_RATE', '44100')
app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3'] = set(
    os.environ.get('AUDIO_FORMATS_TO_CONVERT_TO_MP3', 'wav,flac,m4a,aac,ogg,opus').lower().split(',')
)
if '' in app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3'] and len(app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3']) == 1:
    app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3'] = set()

app.config['VIDEO_MP4_VIDEO_CODEC'] = 'libx264'
app.config['VIDEO_MP4_VIDEO_PRESET'] = os.environ.get('VIDEO_MP4_VIDEO_PRESET', 'veryslow')
app.config['VIDEO_MP4_VIDEO_CRF'] = os.environ.get('VIDEO_MP4_VIDEO_CRF', '16')
app.config['VIDEO_MP4_AUDIO_CODEC'] = os.environ.get('VIDEO_MP4_AUDIO_CODEC', 'aac')
app.config['VIDEO_MP4_AUDIO_BITRATE'] = os.environ.get('VIDEO_MP4_AUDIO_BITRATE', '320k')
app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4'] = set(
    os.environ.get('VIDEO_FORMATS_TO_CONVERT_TO_MP4', 'mkv,mov,avi,wmv,flv').lower().split(',')
)
if '' in app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4'] and len(app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4']) == 1:
    app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4'] = set()

app.config['APP_REDIS_DB_NUM'] = int(os.environ.get('APP_REDIS_DB_NUM', 0))

redis_password_for_celery = os.environ.get('REDIS_PASSWORD', None)
redis_host_for_celery = os.environ.get('REDIS_HOST', 'localhost')
redis_port_for_celery = int(os.environ.get('REDIS_PORT', 6379))
redis_auth_part = f":{redis_password_for_celery}@" if redis_password_for_celery else ""
CELERY_BROKER_URL_CONFIG = f"redis://{redis_auth_part}{redis_host_for_celery}:{redis_port_for_celery}/0"
CELERY_RESULT_BACKEND_CONFIG = f"redis://{redis_auth_part}{redis_host_for_celery}:{redis_port_for_celery}/1"

app.config.update(
    broker_url=CELERY_BROKER_URL_CONFIG,
    result_backend=CELERY_RESULT_BACKEND_CONFIG,
    task_track_started=True,
)
def make_celery(flask_app):
    celery_instance = Celery(
        flask_app.import_name,
        broker=flask_app.config['broker_url'],
        backend=flask_app.config['result_backend']
    )
    celery_instance.conf.update(flask_app.config)
    class ContextTask(celery_instance.Task):
        abstract = True
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)
    celery_instance.Task = ContextTask
    return celery_instance
celery = make_celery(app)

log_level_str = os.environ.get('LOG_LEVEL', 'INFO' if not app.debug else 'DEBUG').upper()
log_level = getattr(logging, log_level_str, logging.INFO)
if not app.logger.handlers:
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
    app.logger.addHandler(stream_handler)
app.logger.setLevel(log_level)
if os.environ.get("FLASK_ENV") == "production":
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.datetime.now().year}

csrf = CSRFProtect(app)

try:
    redis_client = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=app.config['APP_REDIS_DB_NUM'],
        password=os.environ.get('REDIS_PASSWORD', None),
        decode_responses=True, socket_connect_timeout=5,
        socket_keepalive=True, retry_on_timeout=True
    )
    redis_client.ping()
    app.logger.info(f"Flask app successfully connected to Redis DB {app.config['APP_REDIS_DB_NUM']}.")
except Exception as e:
    app.logger.error(f"FATAL: Flask app could not connect to Redis DB {app.config['APP_REDIS_DB_NUM']}: {e}.")
    redis_client = None

def timestamp_to_date_filter(timestamp_str):
    if not timestamp_str: return "N/A"
    try:
        ts = float(timestamp_str)
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError) as e:
        app.logger.debug(f"Error converting timestamp '{timestamp_str}': {e}")
        return "Invalid Date"
app.jinja_env.filters['timestamp_to_date'] = timestamp_to_date_filter

ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'svg', 'avif', 'bmp', 'ico',
    'mp4', 'mkv', 'mov', 'webm', 'ogv', '3gp', '3g2', 'avi', 'wmv', 'flv', 'mpg', 'mpeg',
    'mp3', 'aac', 'wav', 'ogg', 'opus', 'flac', 'm4a', 'wma', 'pdf',
    'zip', 'tar', 'gz', 'tgz', '7z'
}
MEDIA_PROCESSING_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'svg', 'avif', 'bmp', 'ico',
    'mp4', 'mkv', 'mov', 'webm', 'ogv', '3gp', '3g2', 'avi', 'wmv', 'flv', 'mpg', 'mpeg',
    'mp3', 'aac', 'wav', 'ogg', 'opus', 'flac', 'm4a', 'wma', 'pdf'
}
MIME_TYPE_MAP = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif',
    '.webp': 'image/webp', '.heic': 'image/heic', '.heif': 'image/heif', '.svg': 'image/svg+xml',
    '.avif': 'image/avif', '.bmp': 'image/bmp', '.ico': 'image/x-icon',
    '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.mkv': 'video/x-matroska', '.webm': 'video/webm',
    '.ogv': 'video/ogg', '.3gp': 'video/3gpp', '.3g2': 'video/3gpp2', '.avi': 'video/x-msvideo',
    '.wmv': 'video/x-ms-wmv', '.flv': 'video/x-flv', '.mpg': 'video/mpeg', '.mpeg': 'video/mpeg',
    '.mp3': 'audio/mpeg', '.aac': 'audio/aac', '.wav': 'audio/wav', '.ogg': 'audio/ogg',
    '.opus': 'audio/opus', '.flac': 'audio/flac', '.m4a': 'audio/mp4', '.wma': 'audio/x-ms-wma',
    '.pdf': 'application/pdf', '.zip': 'application/zip', '.tar': 'application/x-tar',
    '.gz': 'application/gzip', '.tgz': 'application/gzip', '.7z': 'application/x-7z-compressed',
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_media_for_processing(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in MEDIA_PROCESSING_EXTENSIONS

def get_app_data_redis_client():
    _app_context = current_app._get_current_object() if current_app else None
    host = _app_context.config.get('REDIS_HOST', os.environ.get('REDIS_HOST', 'localhost')) if _app_context else os.environ.get('REDIS_HOST', 'localhost')
    port = int(_app_context.config.get('REDIS_PORT', os.environ.get('REDIS_PORT', 6379))) if _app_context else int(os.environ.get('REDIS_PORT', 6379))
    db_num = _app_context.config.get('APP_REDIS_DB_NUM', 0) if _app_context else int(os.environ.get('APP_REDIS_DB_NUM', 0))
    password = _app_context.config.get('REDIS_PASSWORD', os.environ.get('REDIS_PASSWORD', None)) if _app_context else os.environ.get('REDIS_PASSWORD', None)
    return redis.Redis(host=host, port=port, db=db_num, password=password, decode_responses=True, socket_connect_timeout=5)

if redis_client:
    try:
        if not redis_client.sismember('users', 'admin'):
            admin_password = os.environ.get('LIGHTBOX_ADMIN_PASSWORD', 'ChangeThisDefaultAdminPassw0rd!')
            if admin_password == 'ChangeThisDefaultAdminPassw0rd!':
                 app.logger.warning("SECURITY WARNING: Using default admin password.")
            redis_client.sadd('users', 'admin')
            redis_client.hset('user:admin', mapping={'password_hash': generate_password_hash(admin_password), 'is_admin': '1'})
            app.logger.info("Admin user 'admin' created/verified.")
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error during admin user setup: {e}")
else: app.logger.warning("Redis not connected. Admin user setup skipped.")

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
                app.logger.error(f"Ownership check: No ID for '{item_type}'. Kwargs: {kwargs}")
                flash('Cannot verify ownership: Item ID missing.', 'danger'); return redirect(url_for('index'))
            item_id_to_check_str = str(item_id_to_check)
            item_data_key = f'{item_type}:{item_id_to_check_str}'
            try: item_data = redis_client.hgetall(item_data_key)
            except redis.exceptions.RedisError as e:
                app.logger.error(f"Redis error fetching '{item_data_key}': {e}"); abort(503, description="DB error.")
            if not item_data: flash(f'{item_type.capitalize()} not found.', 'warning'); return redirect(url_for('index'))
            owner_field = 'uploader_user_id' if item_type == 'media' else 'user_id'
            item_owner = item_data.get(owner_field)
            if not item_owner:
                app.logger.error(f"Ownership check: Owner field '{owner_field}' missing for {item_data_key}.")
                flash('Cannot verify ownership: Item data inconsistent.', 'danger'); return redirect(url_for('index'))
            if item_owner != session['username'] and not session.get('is_admin'):
                flash(f'No permission for this {item_type}.', 'danger'); return redirect(url_for('index'))
            item_data['id_str_for_template'] = item_id_to_check_str
            kwargs[f'{item_type}_data'] = item_data
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_unique_disk_path_celery(directory, base_name, extension_with_dot, task_id_for_log=""):
    counter = 0; filename = f"{base_name}{extension_with_dot}"; path = os.path.join(directory, filename)
    _base = base_name
    while os.path.exists(path):
        counter += 1; filename = f"{_base}_{counter}{extension_with_dot}"; path = os.path.join(directory, filename)
        if counter > 100:
            _task_logger = current_app.logger if current_app else logging.getLogger(__name__)
            _task_logger.error(f"[Task {task_id_for_log}] High collision finding unique path for {base_name}{extension_with_dot}. Using UUID.")
            filename = f"{uuid.uuid4().hex}{extension_with_dot}"; path = os.path.join(directory, filename); break
    return path, filename

@celery.task(bind=True, name='app.convert_video_to_mp4_task', max_retries=3, default_retry_delay=120)
def convert_video_to_mp4_task(self, original_video_temp_path, target_mp4_disk_path, media_id_for_update, batch_id_for_update, original_filename_for_log, disk_path_segment_for_batch, uploader_username_for_log):
    task_id = self.request.id; logger = current_app.logger
    logger.info(f"[VideoTask {task_id}] User:{uploader_username_for_log} Video->MP4: {original_filename_for_log} (MediaID:{media_id_for_update})")
    ffmpeg_path = current_app.config.get('FFMPEG_PATH', 'ffmpeg')
    vid_codec = current_app.config.get('VIDEO_MP4_VIDEO_CODEC'); vid_preset = current_app.config.get('VIDEO_MP4_VIDEO_PRESET')
    vid_crf = current_app.config.get('VIDEO_MP4_VIDEO_CRF'); aud_codec = current_app.config.get('VIDEO_MP4_AUDIO_CODEC')
    aud_bitrate = current_app.config.get('VIDEO_MP4_AUDIO_BITRATE')
    ffmpeg_command = [ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-i', original_video_temp_path, '-c:v', vid_codec, '-preset', vid_preset, '-crf', vid_crf, '-c:a', aud_codec, '-b:a', aud_bitrate, '-movflags', '+faststart', '-f', 'mp4', '-y', target_mp4_disk_path]
    status_update = {'processing_status': 'failed', 'error_message': 'Unknown video conversion error.'}
    try:
        logger.info(f"[VideoTask {task_id}] Executing: {' '.join(ffmpeg_command)}")
        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, timeout=10800)
        logger.info(f"[VideoTask {task_id}] Success: {original_filename_for_log}")
        final_name = os.path.basename(target_mp4_disk_path)
        final_rpath = os.path.join(disk_path_segment_for_batch, final_name)
        status_update = {'filename_on_disk': final_name, 'filepath': final_rpath, 'mimetype': 'video/mp4', 'processing_status': 'completed', 'error_message': ''}
        get_app_data_redis_client().hmset(f'media:{media_id_for_update}', status_update)
        logger.info(f"[VideoTask {task_id}] Redis updated for MediaID {media_id_for_update}.")
        return {'status': 'success', 'output_path': target_mp4_disk_path, 'media_id': media_id_for_update}
    except subprocess.CalledProcessError as e:
        err_out = e.stderr.strip() if e.stderr else "No stderr."; logger.error(f"[VideoTask {task_id}] FAILED (rc {e.returncode}): {original_filename_for_log}. Error: {err_out}")
        status_update.update({'error_message': f'Video conv. error (rc {e.returncode}): {err_out[:200]}'})
        if self.request.retries < self.max_retries: logger.info(f"[VideoTask {task_id}] Retrying ({self.request.retries + 1}/{self.max_retries})"); raise self.retry(exc=e, countdown=int(self.default_retry_delay * (2**self.request.retries)))
        raise
    except subprocess.TimeoutExpired as e:
        logger.error(f"[VideoTask {task_id}] TIMEOUT: {original_filename_for_log}"); status_update.update({'error_message': 'Video conversion timeout.'})
        if self.request.retries < self.max_retries: logger.info(f"[VideoTask {task_id}] Retrying ({self.request.retries + 1}/{self.max_retries})"); raise self.retry(exc=e, countdown=int(self.default_retry_delay * (2**self.request.retries)))
        raise
    except Exception as e:
        logger.error(f"[VideoTask {task_id}] Unexpected error: {e}", exc_info=True); status_update.update({'error_message': f'Unexpected error: {str(e)[:100]}'}); raise
    finally:
        r_client = get_app_data_redis_client()
        try:
            if r_client.hget(f'media:{media_id_for_update}', 'processing_status') != 'completed': r_client.hmset(f'media:{media_id_for_update}', status_update)
            logger.info(f"[VideoTask {task_id}] Final Redis status for MediaID {media_id_for_update}: {status_update.get('processing_status', 'N/A')}")
        except Exception as e_redis: logger.error(f"[VideoTask {task_id}] CRITICAL: Failed Redis update in finally: {e_redis}")
        if os.path.exists(original_video_temp_path):
            try: os.remove(original_video_temp_path); logger.info(f"[VideoTask {task_id}] Cleaned temp: {original_video_temp_path}")
            except OSError as e_rm: logger.error(f"[VideoTask {task_id}] Error removing temp: {e_rm}")

@celery.task(bind=True, name='app.transcode_audio_to_mp3_task', max_retries=3, default_retry_delay=60)
def transcode_audio_to_mp3_task(self, original_audio_temp_path, target_mp3_disk_path, media_id_for_update, batch_id_for_update, original_filename_for_log, disk_path_segment_for_batch, uploader_username_for_log):
    task_id = self.request.id; logger = current_app.logger
    logger.info(f"[AudioTask {task_id}] User:{uploader_username_for_log} Audio->MP3: {original_filename_for_log} (MediaID:{media_id_for_update})")
    ffmpeg_path = current_app.config.get('FFMPEG_PATH', 'ffmpeg')
    mp3_encoder = current_app.config.get('AUDIO_MP3_ENCODER'); mp3_options = current_app.config.get('AUDIO_MP3_OPTIONS')
    mp3_sample_rate = current_app.config.get('AUDIO_MP3_SAMPLE_RATE')
    ffmpeg_command = [ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-i', original_audio_temp_path, '-c:a', mp3_encoder]
    ffmpeg_command.extend(mp3_options)
    if mp3_sample_rate: ffmpeg_command.extend(['-ar', mp3_sample_rate])
    ffmpeg_command.extend(['-f', 'mp3', '-y', target_mp3_disk_path])
    status_update = {'processing_status': 'failed', 'error_message': 'Unknown audio to MP3 error.'}
    try:
        logger.info(f"[AudioTask {task_id}] Executing: {' '.join(ffmpeg_command)}")
        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, timeout=3600)
        logger.info(f"[AudioTask {task_id}] Success: {original_filename_for_log}")
        final_name = os.path.basename(target_mp3_disk_path)
        final_rpath = os.path.join(disk_path_segment_for_batch, final_name)
        status_update = {'filename_on_disk': final_name, 'filepath': final_rpath, 'mimetype': 'audio/mpeg', 'processing_status': 'completed', 'error_message': ''}
        get_app_data_redis_client().hmset(f'media:{media_id_for_update}', status_update)
        logger.info(f"[AudioTask {task_id}] Redis updated for MediaID {media_id_for_update}.")
        return {'status': 'success', 'output_path': target_mp3_disk_path, 'media_id': media_id_for_update}
    except subprocess.CalledProcessError as e:
        err_out = e.stderr.strip() if e.stderr else "No stderr."; logger.error(f"[AudioTask {task_id}] FAILED (rc {e.returncode}): {original_filename_for_log}. Error: {err_out}")
        status_update.update({'error_message': f'Audio conv. error (rc {e.returncode}): {err_out[:200]}'})
        if self.request.retries < self.max_retries: logger.info(f"[AudioTask {task_id}] Retrying ({self.request.retries + 1}/{self.max_retries})"); raise self.retry(exc=e, countdown=int(self.default_retry_delay * (2**self.request.retries)))
        raise
    except subprocess.TimeoutExpired as e:
        logger.error(f"[AudioTask {task_id}] TIMEOUT: {original_filename_for_log}"); status_update.update({'error_message': 'Audio conversion timeout.'})
        if self.request.retries < self.max_retries: logger.info(f"[AudioTask {task_id}] Retrying ({self.request.retries + 1}/{self.max_retries})"); raise self.retry(exc=e, countdown=int(self.default_retry_delay * (2**self.request.retries)))
        raise
    except Exception as e:
        logger.error(f"[AudioTask {task_id}] Unexpected error: {e}", exc_info=True); status_update.update({'error_message': f'Unexpected error: {str(e)[:100]}'}); raise
    finally:
        r_client = get_app_data_redis_client()
        try:
            if r_client.hget(f'media:{media_id_for_update}', 'processing_status') != 'completed': r_client.hmset(f'media:{media_id_for_update}', status_update)
            logger.info(f"[AudioTask {task_id}] Final Redis status for MediaID {media_id_for_update}: {status_update.get('processing_status', 'N/A')}")
        except Exception as e_redis: logger.error(f"[AudioTask {task_id}] CRITICAL: Failed Redis update in finally: {e_redis}")
        if os.path.exists(original_audio_temp_path):
            try: os.remove(original_audio_temp_path); logger.info(f"[AudioTask {task_id}] Cleaned temp: {original_audio_temp_path}")
            except OSError as e_rm: logger.error(f"[AudioTask {task_id}] Error removing temp: {e_rm}")

@celery.task(bind=True, name='app.handle_zip_import_task', max_retries=1, default_retry_delay=60)
def handle_zip_import_task(self, uploaded_zip_filepath_on_disk, target_batch_id, uploader_username_for_log, original_zip_filename_for_log):
    task_id = self.request.id; logger = current_app.logger; app_config = current_app.config; task_redis_client = get_app_data_redis_client()
    logger.info(f"[ZIPImportTask {task_id}] User:{uploader_username_for_log} Import: {original_zip_filename_for_log} for BatchID:{target_batch_id}")
    batch_owner_username = task_redis_client.hget(f'batch:{target_batch_id}', 'user_id')
    if not batch_owner_username:
        logger.error(f"[ZIPImportTask {task_id}] No owner for batch {target_batch_id}. Aborting.");
        zip_item_id = task_redis_client.hget(f'batch_import_tracker:{target_batch_id}:{original_zip_filename_for_log}', 'zip_media_id')
        if zip_item_id: task_redis_client.hmset(f'media:{zip_item_id}', {'processing_status': 'failed_import', 'error_message': 'Batch owner not found.'})
        return {'status': 'error', 'message': 'Batch owner missing.'}
    disk_path_segment_for_batch = os.path.join(batch_owner_username, target_batch_id)
    full_disk_upload_dir_for_batch_contents = os.path.join(app_config['UPLOAD_FOLDER'], disk_path_segment_for_batch)
    os.makedirs(full_disk_upload_dir_for_batch_contents, exist_ok=True)
    temp_extract_base_path = os.path.join(app_config['UPLOAD_FOLDER'], "temp_zip_extracts")
    os.makedirs(temp_extract_base_path, exist_ok=True)
    temp_extract_path_for_this_zip = os.path.join(temp_extract_base_path, f"import_{target_batch_id}_{uuid.uuid4().hex}")
    os.makedirs(temp_extract_path_for_this_zip, exist_ok=True)
    imported_media_count = 0; imported_blob_count = 0; manifest_data = None
    zip_item_id_from_tracker = task_redis_client.hget(f'batch_import_tracker:{target_batch_id}:{original_zip_filename_for_log}', 'zip_media_id')
    try:
        with zipfile.ZipFile(uploaded_zip_filepath_on_disk, 'r') as zip_ref:
            if 'lightbox_manifest.json' in zip_ref.namelist():
                with zip_ref.open('lightbox_manifest.json') as mf:
                    try: manifest_data = json.load(mf); logger.info(f"[ZIPImportTask {task_id}] Manifest loaded.")
                    except json.JSONDecodeError as e: logger.warning(f"[ZIPImportTask {task_id}] Manifest corrupted: {e}")
            redis_pipe = task_redis_client.pipeline()
            for member in zip_ref.infolist():
                if member.is_dir() or member.filename.startswith('__MACOSX') or member.filename.endswith('/'): continue
                member_zip_path = member.filename
                member_sane_basename = secure_filename(os.path.basename(member_zip_path))
                if not member_sane_basename: logger.warning(f"[ZIPImportTask {task_id}] Skipped empty filename in ZIP: {member_zip_path}"); continue
                extracted_temp_path = os.path.join(temp_extract_path_for_this_zip, member_sane_basename)
                if not os.path.abspath(extracted_temp_path).startswith(os.path.abspath(temp_extract_path_for_this_zip)):
                    logger.error(f"[ZIPImportTask {task_id}] Path traversal: {member_zip_path}. Skipping."); continue
                os.makedirs(os.path.dirname(extracted_temp_path), exist_ok=True)
                with zip_ref.open(member) as src, open(extracted_temp_path, "wb") as dest: shutil.copyfileobj(src, dest)
                orig_fname_redis = member_zip_path; desc_redis = ""; hidden_redis = '0'
                if manifest_data and 'files' in manifest_data:
                    for item_mf in manifest_data.get('files', []):
                        if item_mf.get('zip_path') == member_zip_path:
                            orig_fname_redis = item_mf.get('original_filename', member_zip_path)
                            desc_redis = item_mf.get('description', ''); hidden_redis = '1' if item_mf.get('is_hidden', False) else '0'; break
                base_sane, ext_dot = os.path.splitext(orig_fname_redis); ext_dot = ext_dot.lower(); item_id = str(uuid.uuid4())
                sec_base = secure_filename(base_sane) if base_sane else f"media_{item_id[:8]}"
                common_data = {'original_filename': orig_fname_redis, 'filename_on_disk': "", 'filepath': "", 'mimetype': MIME_TYPE_MAP.get(ext_dot, 'application/octet-stream'), 'is_hidden': hidden_redis, 'is_liked': '0', 'uploader_user_id': uploader_username_for_log, 'batch_id': target_batch_id, 'upload_timestamp': datetime.datetime.now().timestamp(), 'description': desc_redis, 'item_type': 'media'}
                if is_media_for_processing(orig_fname_redis):
                    celery_input_path = extracted_temp_path
                    if ext_dot.lstrip('.') in app_config['VIDEO_FORMATS_TO_CONVERT_TO_MP4']:
                        target_path, _ = get_unique_disk_path_celery(full_disk_upload_dir_for_batch_contents, sec_base, ".mp4", task_id)
                        redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': os.path.basename(celery_input_path), 'filepath': os.path.join(disk_path_segment_for_batch, os.path.basename(celery_input_path)), 'processing_status': 'queued'})
                        convert_video_to_mp4_task.apply_async(args=[celery_input_path, target_path, item_id, target_batch_id, orig_fname_redis, disk_path_segment_for_batch, uploader_username_for_log])
                        imported_media_count += 1
                    elif ext_dot.lstrip('.') in app_config['AUDIO_FORMATS_TO_CONVERT_TO_MP3']:
                        target_path, _ = get_unique_disk_path_celery(full_disk_upload_dir_for_batch_contents, sec_base, ".mp3", task_id)
                        redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': os.path.basename(celery_input_path), 'filepath': os.path.join(disk_path_segment_for_batch, os.path.basename(celery_input_path)), 'processing_status': 'queued'})
                        transcode_audio_to_mp3_task.apply_async(args=[celery_input_path, target_path, item_id, target_batch_id, orig_fname_redis, disk_path_segment_for_batch, uploader_username_for_log])
                        imported_media_count += 1
                    else:
                        final_path, final_name = get_unique_disk_path_celery(full_disk_upload_dir_for_batch_contents, sec_base, ext_dot, task_id)
                        shutil.move(extracted_temp_path, final_path)
                        redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': final_name, 'filepath': os.path.join(disk_path_segment_for_batch, final_name), 'processing_status': 'completed'})
                        imported_media_count += 1
                else:
                    final_path, final_name = get_unique_disk_path_celery(full_disk_upload_dir_for_batch_contents, member_sane_basename, ext_dot, task_id) # Use original ext for blobs
                    shutil.move(extracted_temp_path, final_path)
                    redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': final_name, 'filepath': os.path.join(disk_path_segment_for_batch, final_name), 'processing_status': 'completed', 'item_type': 'blob'})
                    imported_blob_count += 1
                redis_pipe.rpush(f'batch:{target_batch_id}:media_ids', item_id)
            redis_pipe.execute()
            logger.info(f"[ZIPImportTask {task_id}] Imported {imported_media_count} media, {imported_blob_count} blobs into batch {target_batch_id}.")
            if zip_item_id_from_tracker: task_redis_client.hmset(f'media:{zip_item_id_from_tracker}', {'processing_status': 'completed_import', 'error_message': ''})
    except zipfile.BadZipFile:
        logger.error(f"[ZIPImportTask {task_id}] Bad ZIP: {original_zip_filename_for_log}")
        if zip_item_id_from_tracker: task_redis_client.hmset(f'media:{zip_item_id_from_tracker}', {'processing_status': 'failed_import', 'error_message': 'Corrupted ZIP.'})
    except Exception as e:
        logger.error(f"[ZIPImportTask {task_id}] Error processing ZIP {original_zip_filename_for_log}: {e}", exc_info=True)
        if zip_item_id_from_tracker: task_redis_client.hmset(f'media:{zip_item_id_from_tracker}', {'processing_status': 'failed_import', 'error_message': f'Import error: {str(e)[:100]}'})
    finally:
        if os.path.exists(temp_extract_path_for_this_zip): shutil.rmtree(temp_extract_path_for_this_zip)
        if zip_item_id_from_tracker: task_redis_client.delete(f'batch_import_tracker:{target_batch_id}:{original_zip_filename_for_log}')
    return {'status': 'success', 'imported_media': imported_media_count, 'imported_blobs': imported_blob_count, 'batch_id': target_batch_id}

@app.route('/index') # This is already defined, assuming your original / route is the same
@app.route('/')
@login_required
def index():
    if not redis_client: flash('DB service unavailable.', 'danger'); return render_template('index.html', batches=[], upload_form_hint="Uploads unavailable.")
    username = session['username']
    try:
        batch_ids = redis_client.lrange(f'user:{username}:batches', 0, -1)
        batches_data = []
        for batch_id in batch_ids:
            batch_info = redis_client.hgetall(f'batch:{batch_id}')
            if batch_info: batch_info['id'] = batch_id; batch_info['item_count'] = redis_client.llen(f'batch:{batch_id}:media_ids'); batches_data.append(batch_info)
        batches_data.sort(key=lambda x: float(x.get('creation_timestamp', 0)), reverse=True)
        return render_template('index.html', batches=batches_data, upload_form_hint="Upload media, import archives, or store files.")
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error for user {username} on index: {e}"); flash('Error retrieving lightboxes.', 'danger')
        return render_template('index.html', batches=[], upload_form_hint="Error loading data.")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('username'): return redirect(url_for('index'))
    if request.method == 'POST':
        if not redis_client: flash('Registration unavailable.', 'danger'); return render_template('register.html')
        username = request.form.get('username','').strip(); password = request.form.get('password'); confirm_password = request.form.get('confirm_password')
        if not all([username, password, confirm_password]): flash('All fields required.', 'danger'); return render_template('register.html')
        if len(username) < 3: flash('Username too short.', 'danger'); return render_template('register.html')
        if password != confirm_password: flash('Passwords do not match.', 'danger'); return render_template('register.html')
        if len(password) < 8: flash('Password too short (min 8 chars).', 'danger'); return render_template('register.html')
        try:
            if redis_client.sismember('users', username): flash('Username exists.', 'danger'); return render_template('register.html')
            pipe = redis_client.pipeline(); pipe.sadd('users', username); pipe.hset(f'user:{username}', mapping={'password_hash': generate_password_hash(password), 'is_admin': '0'}); pipe.execute()
            app.logger.info(f"New user: {username}"); flash('Registration successful! Please log in.', 'success'); return redirect(url_for('login'))
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error for {username}: {e}"); flash('Registration error.', 'danger')
    return render_template('register.html')

@app.route('/about')
def about_page(): return render_template('about.html')
@app.route('/ross-nesbitt')
def ross_nesbitt_profile(): return render_template('rossnesbitt.html')
@app.route('/why-lightbox')
def why_lightbox_page(): return render_template('why.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('username'): return redirect(url_for('index'))
    if request.method == 'POST':
        if not redis_client: flash('Login unavailable.', 'danger'); return render_template('login.html')
        username = request.form.get('username'); password = request.form.get('password')
        try:
            if not redis_client.sismember('users', username): flash('Invalid credentials.', 'danger'); return render_template('login.html')
            user_data = redis_client.hgetall(f'user:{username}')
            if not user_data or not check_password_hash(user_data.get('password_hash',''), password): flash('Invalid credentials.', 'danger'); return render_template('login.html')
            session['username'] = username; session['is_admin'] = user_data.get('is_admin') == '1'; session.permanent = True
            app.logger.info(f"User '{username}' logged in."); flash(f'Welcome back, {username}!', 'success')
            next_url = request.args.get('next')
            if next_url and url_parse(next_url).netloc == '' and url_parse(next_url).scheme == '': return redirect(next_url)
            return redirect(url_for('index'))
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error for {username}: {e}"); flash('Login error.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    username = session.pop('username', 'UnknownUser'); session.clear(); app.logger.info(f"User '{username}' logged out.")
    flash('Logged out successfully.', 'info'); return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if not redis_client: flash('DB unavailable.', 'danger'); return redirect(request.referrer or url_for('index'))
    if 'files[]' not in request.files: flash('No file part.', 'danger'); return redirect(request.referrer or url_for('index'))
    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files): flash('No files selected.', 'danger'); return redirect(request.referrer or url_for('index'))

    current_user = session['username']; existing_batch_id = request.form.get('existing_batch_id')
    upload_type = request.form.get('upload_type', 'media')
    app.logger.info(f"Upload by {current_user}. Type: {upload_type}. Files: {[f.filename for f in files if f.filename]}")

    batch_id, batch_name, new_batch, batch_owner = "", "", True, current_user
    if existing_batch_id:
        new_batch = False; batch_id = existing_batch_id
        try:
            b_info = redis_client.hgetall(f'batch:{batch_id}')
            if not b_info: flash(f'Batch {batch_id} not found.', 'danger'); return redirect(request.referrer or url_for('index'))
            batch_owner = b_info.get('user_id')
            if not batch_owner: app.logger.error(f"Batch {batch_id} missing owner."); flash('Batch data error.', 'danger'); return redirect(request.referrer or url_for('index'))
            if batch_owner != current_user and not session.get('is_admin'): flash('No permission.', 'danger'); return redirect(request.referrer or url_for('index'))
            batch_name = b_info.get('name', f'Batch_{batch_id[:8]}')
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error batch {batch_id}: {e}"); flash("DB error.", "danger"); return redirect(request.referrer or url_for('index'))
    else:
        new_batch = True; batch_name_form = request.form.get('batch_name', '').strip(); batch_id = str(uuid.uuid4())
        if upload_type == 'import_zip' and not batch_name_form and files and files[0].filename:
            zip_base, _ = os.path.splitext(files[0].filename); batch_name = secure_filename(zip_base) if zip_base else f"Import_{batch_id[:8]}"
        elif batch_name_form: batch_name = batch_name_form
        else:
            if upload_type != 'import_zip': flash('New batch name required.', 'warning'); return redirect(request.referrer or url_for('index'))
            batch_name = f"Imported_{batch_id[:8]}" # Fallback for import_zip
            
    disk_path_segment = os.path.join(batch_owner, batch_id)
    full_disk_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], disk_path_segment)
    try: os.makedirs(full_disk_dir, exist_ok=True)
    except OSError as e: app.logger.error(f"Error creating dir '{full_disk_dir}': {e}"); flash("Server dir error.", "danger"); return redirect(request.referrer or url_for('index'))

    direct_count, convert_queued_count, import_queued_count, blob_count = 0,0,0,0
    redis_pipe = redis_client.pipeline()
    vid_formats = app.config['VIDEO_FORMATS_TO_CONVERT_TO_MP4']; aud_formats = app.config['AUDIO_FORMATS_TO_CONVERT_TO_MP3']

    def get_unique_disk_path(directory, base, ext_dot): # Local helper for /upload
        ct = 0; fname = f"{base}{ext_dot}"; pth = os.path.join(directory, fname); _b = base
        while os.path.exists(pth): ct += 1; fname = f"{_b}_{ct}{ext_dot}"; pth = os.path.join(directory, fname)
        if ct > 100: fname = f"{_b}_{uuid.uuid4().hex[:8]}{ext_dot}"; pth = os.path.join(directory,fname)
        return pth, fname

    for file_item in files:
        if not file_item or not file_item.filename: continue
        orig_fname = file_item.filename
        if not allowed_file(orig_fname):
            if orig_fname: flash(f'File type "{orig_fname}" not allowed. Skipped.', 'warning'); continue
        base, ext_dot = os.path.splitext(orig_fname); ext_dot = ext_dot.lower(); ext_no_dot = ext_dot.lstrip('.')
        item_id = str(uuid.uuid4()); sec_base = secure_filename(base) if base else f"item_{item_id[:8]}"
        temp_input_fname = f"{item_id}_input{ext_dot}"; temp_input_path = os.path.join(full_disk_dir, temp_input_fname)
        initial_rpath_temp = os.path.join(disk_path_segment, temp_input_fname)
        common_data = {'original_filename': orig_fname, 'filename_on_disk': "", 'filepath': "", 'mimetype': MIME_TYPE_MAP.get(ext_dot, 'application/octet-stream'), 'is_hidden': '0', 'is_liked': '0', 'uploader_user_id': current_user, 'batch_id': batch_id, 'upload_timestamp': datetime.datetime.now().timestamp(), 'item_type': 'media'}
        try:
            if upload_type == 'import_zip' and ext_no_dot == 'zip':
                app.logger.info(f"Queuing ZIP '{orig_fname}' for import. ItemID: {item_id}")
                file_item.save(temp_input_path)
                redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': temp_input_fname, 'filepath': initial_rpath_temp, 'processing_status': 'queued_import', 'item_type': 'archive_import'})
                redis_pipe.hmset(f'batch_import_tracker:{batch_id}:{orig_fname}', {'zip_media_id': item_id})
                handle_zip_import_task.apply_async(args=[temp_input_path, batch_id, current_user, orig_fname])
                import_queued_count += 1
            elif upload_type == 'blob_storage' or not is_media_for_processing(orig_fname):
                app.logger.info(f"Storing blob: '{orig_fname}'. ItemID: {item_id}")
                final_path, final_name = get_unique_disk_path(full_disk_dir, sec_base, ext_dot)
                file_item.save(final_path)
                redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': final_name, 'filepath': os.path.join(disk_path_segment, final_name), 'processing_status': 'completed', 'item_type': 'blob'})
                blob_count += 1
            elif upload_type == 'media' and is_media_for_processing(orig_fname):
                if ext_no_dot in vid_formats:
                    file_item.save(temp_input_path); target_path, _ = get_unique_disk_path(full_disk_dir, sec_base, ".mp4")
                    redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': temp_input_fname, 'filepath': initial_rpath_temp, 'processing_status': 'queued'})
                    convert_video_to_mp4_task.apply_async(args=[temp_input_path, target_path, item_id, batch_id, orig_fname, disk_path_segment, current_user])
                    convert_queued_count += 1
                elif ext_no_dot in aud_formats:
                    file_item.save(temp_input_path); target_path, _ = get_unique_disk_path(full_disk_dir, sec_base, ".mp3")
                    redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': temp_input_fname, 'filepath': initial_rpath_temp, 'processing_status': 'queued'})
                    transcode_audio_to_mp3_task.apply_async(args=[temp_input_path, target_path, item_id, batch_id, orig_fname, disk_path_segment, current_user])
                    convert_queued_count += 1
                else:
                    final_path, final_name = get_unique_disk_path(full_disk_dir, sec_base, ext_dot)
                    file_item.save(final_path)
                    redis_pipe.hmset(f'media:{item_id}', {**common_data, 'filename_on_disk': final_name, 'filepath': os.path.join(disk_path_segment, final_name), 'processing_status': 'completed'})
                    direct_count += 1
            else: flash(f"Could not handle '{orig_fname}'. Skipped.", "warning"); continue
            redis_pipe.rpush(f'batch:{batch_id}:media_ids', item_id)
        except Exception as e:
            app.logger.error(f"Error processing '{orig_fname}' (type:{upload_type}): {e}", exc_info=True); flash(f"Error with '{orig_fname}'. Skipped.", "danger")
            if os.path.exists(temp_input_path): # CORRECTED INDENTATION FOR THIS BLOCK
                try:
                    os.remove(temp_input_path)
                except OSError:
                    app.logger.error(f"Failed to cleanup temp file during error: {temp_input_path}")
    
    # CORRECTED INDENTATION FOR THIS BLOCK
    try:
        redis_pipe.execute() 
    except redis.exceptions.RedisError as e: 
        app.logger.error(f"Redis pipeline error batch {batch_id}: {e}")
        flash("Database error during upload.", "danger")
        return redirect(request.referrer or url_for('index'))

    total_submitted = direct_count + convert_queued_count + import_queued_count + blob_count
    if total_submitted > 0:
        try:
            if new_batch:
                redis_client.hset(f'batch:{batch_id}', mapping={'user_id': batch_owner, 'creation_timestamp': datetime.datetime.now().timestamp(), 'name': batch_name, 'is_shared': '0', 'share_token': ''})
                redis_client.lpush(f'user:{batch_owner}:batches', batch_id)
            else: redis_client.hset(f'batch:{batch_id}', 'last_modified_timestamp', datetime.datetime.now().timestamp())
            msg = [f'{total_submitted} item(s) for "{batch_name}".']
            if convert_queued_count: msg.append(f"{convert_queued_count} media processing.")
            if import_queued_count: msg.append(f"{import_queued_count} archive(s) importing.")
            if blob_count: msg.append(f"{blob_count} file(s) stored.")
            flash(' '.join(msg), 'success'); return redirect(url_for('collection_view', batch_id=batch_id))
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error finalizing batch {batch_id}: {e}"); flash("Items submitted, error saving batch.", "warning"); return redirect(url_for('index'))
    else:
        if new_batch and os.path.exists(full_disk_dir) and not os.listdir(full_disk_dir):
            try: shutil.rmtree(full_disk_dir)
            except OSError as e_rmdir: app.logger.error(f"Error removing empty new batch dir '{full_disk_dir}': {e_rmdir}")
        flash('No valid files processed.', 'info'); return redirect(request.referrer or url_for('index'))

@app.route('/batch/<uuid:batch_id>')
@login_required
@owner_or_admin_access_required(item_type='batch')
def collection_view(batch_id, batch_data):
    if not redis_client: flash('DB unavailable.', 'danger'); return redirect(url_for('index'))
    try:
        batch_info = batch_data; batch_id_str = str(batch_id); batch_info['id'] = batch_id_str
        batch_info['is_shared_val'] = batch_info.get('is_shared', '0'); batch_info['share_token_val'] = batch_info.get('share_token', '')
        if batch_info.get('is_shared') == '1' and batch_info.get('share_token'): batch_info['public_share_url'] = url_for('public_batch_view', share_token=batch_info['share_token_val'], _external=True)
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1)
        media_list = []; valid_slideshow_media = 0; any_processing = False
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata:
                mdata['id'] = mid; status = mdata.get('processing_status', 'completed'); mdata['processing_status'] = status
                mdata['error_message'] = mdata.get('error_message', ''); mdata['item_type'] = mdata.get('item_type', 'media')
                if status not in ['completed', 'failed', 'completed_import', 'failed_import']: any_processing = True
                rpath = mdata.get('filepath')
                if rpath:
                    if mdata['item_type'] in ['blob', 'archive_import']: mdata['download_url'] = url_for('download_item', batch_id=batch_id_str, media_id=mid); mdata['web_path'] = None
                    else: mdata['web_path'] = url_for('static', filename=f"uploads/{rpath.lstrip('/')}"); mdata['download_url'] = url_for('download_item', batch_id=batch_id_str, media_id=mid)
                else: mdata['web_path'] = None; mdata['download_url'] = None;
                if status == 'completed' and mdata['item_type'] != 'blob' and mdata['item_type'] != 'archive_import': app.logger.warning(f"CollView: Completed media {mid} batch {batch_id_str} missing filepath.")
                media_list.append(mdata)
                if mdata['item_type'] == 'media' and status == 'completed' and mdata.get('is_hidden','0') == '0': valid_slideshow_media +=1
            else: app.logger.warning(f"Media ID {mid} in batch {batch_id_str} but no data in Redis.")
        batch_info['valid_media_for_slideshow_count'] = valid_slideshow_media; batch_info['total_items_count'] = len(media_ids)
        return render_template('collection.html', batch=batch_info, media_items=media_list, is_any_item_processing=any_processing)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error collection_view batch {str(batch_id)}: {e}"); flash("DB error.",'danger'); return redirect(url_for('index'))
    except Exception as e: app.logger.error(f"Error collection_view batch {str(batch_id)}: {e}", exc_info=True); flash("Error loading.", "danger"); return redirect(url_for('index'))

@app.route('/slideshow/<uuid:batch_id>')
@login_required
@owner_or_admin_access_required(item_type='batch')
def slideshow(batch_id, batch_data):
    if not redis_client: flash('DB unavailable.', 'danger'); return redirect(url_for('collection_view', batch_id=str(batch_id)) if batch_id else url_for('index'))
    try:
        batch_info = batch_data; batch_id_str = str(batch_id); batch_info['id'] = batch_id_str
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1); js_media_list = []
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata and mdata.get('is_hidden','0')=='0' and mdata.get('processing_status','completed')=='completed' and mdata.get('item_type','media')=='media':
                rpath = mdata.get('filepath'); mimetype = mdata.get('mimetype')
                if rpath and mimetype and mimetype.startswith(('image/','video/','audio/')):
                    js_media_list.append({'filepath':url_for('static',filename=f"uploads/{rpath.lstrip('/')}"), 'mimetype':mimetype, 'original_filename':mdata.get('original_filename','unknown')})
        if not js_media_list: flash("No playable items.", "info"); return redirect(url_for('collection_view', batch_id=batch_id_str))
        return render_template('slideshow.html', batch=batch_info, media_data_json=json.dumps(js_media_list), is_public_view=False)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error slideshow {str(batch_id)}: {e}"); flash("DB error.",'danger'); return redirect(url_for('collection_view', batch_id=str(batch_id)))
    except Exception as e: app.logger.error(f"Error slideshow {str(batch_id)}: {e}", exc_info=True); flash("Error loading.", "danger"); return redirect(url_for('collection_view', batch_id=str(batch_id)))

@app.route('/batch/<string:batch_id>/toggle_share', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='batch')
def toggle_share_batch(batch_id, batch_data):
    if not redis_client: abort(503, description="DB unavailable.")
    batch_id_str = str(batch_id); token = batch_data.get('share_token'); shared_str = batch_data.get('is_shared', '0')
    new_shared = not (shared_str == '1'); update = {'is_shared': '1' if new_shared else '0'}
    pipe = redis_client.pipeline()
    if new_shared:
        if not token: token = secrets.token_urlsafe(24); update['share_token'] = token; pipe.set(f'share_token:{token}', batch_id_str)
    elif token: pipe.delete(f'share_token:{token}'); update['share_token'] = ''
    pipe.hmset(f'batch:{batch_id_str}', update); pipe.execute(); name = batch_data.get('name', batch_id_str)
    app.logger.info(f"Batch '{name}' sharing: {'Public' if new_shared else 'Private'}")
    if new_shared and token: flash(f'Batch "{name}" <strong>Public</strong>. Link: <a href="{url_for("public_batch_view", share_token=token, _external=True)}" target="_blank" class="alert-link" style="word-break: break-all;">{url_for("public_batch_view", share_token=token, _external=True)}</a>', 'success')
    else: flash(f'Batch "{name}" <strong>Private</strong>. Links deactivated.', 'info')
    return redirect(url_for('collection_view', batch_id=batch_id_str))

@app.route('/public/batch/<share_token>')
def public_batch_view(share_token):
    if not redis_client: abort(503, description="DB unavailable.")
    try:
        batch_id_str = redis_client.get(f'share_token:{share_token}')
        if not batch_id_str: app.logger.warning(f"Invalid token: {share_token}"); return render_template('public_link_invalid.html', reason="Link invalid/expired."), 404
        batch_info = redis_client.hgetall(f'batch:{batch_id_str}')
        if not batch_info or batch_info.get('is_shared', '0') != '1': app.logger.warning(f"Access attempt non-shared batch {batch_id_str}"); return render_template('public_link_invalid.html', reason="Batch not shared."), 403
        batch_info['id'] = batch_id_str; batch_info['share_token'] = share_token
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1); media_list = []; valid_items = 0
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata and mdata.get('is_hidden','0')=='0' and mdata.get('processing_status','completed')=='completed':
                mdata['id'] = mid; mdata['item_type'] = mdata.get('item_type','media'); rpath = mdata.get('filepath')
                if rpath:
                    if mdata['item_type'] in ['blob','archive_import']: mdata['is_downloadable_blob_public'] = (mdata['item_type'] == 'blob'); mdata['public_download_url'] = url_for('public_download_item', share_token=share_token, media_id=mid, _external=True) if mdata['item_type'] == 'blob' else None; mdata['web_path'] = None
                    else: mdata['web_path'] = url_for('static',filename=f"uploads/{rpath.lstrip('/')}")
                    media_list.append(mdata); valid_items+=1
                elif mdata.get('processing_status')=='completed': app.logger.warning(f"PublicView: Completed item {mid} missing filepath.")
        batch_info['item_count'] = valid_items
        return render_template('public_view.html', batch=batch_info, media_items=media_list)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error public_batch_view {share_token}: {e}"); return render_template('public_link_invalid.html', reason="DB error."), 500
    except Exception as e: app.logger.error(f"Error public_batch_view {share_token}: {e}", exc_info=True); return render_template('public_link_invalid.html', reason="Error."), 500

@app.route('/public/slideshow/<share_token>')
def public_slideshow_view(share_token):
    if not redis_client: abort(503, description="DB unavailable.")
    try:
        batch_id_str = redis_client.get(f'share_token:{share_token}')
        if not batch_id_str: return render_template('public_link_invalid.html', reason="Invalid link."), 404
        batch_info = redis_client.hgetall(f'batch:{batch_id_str}')
        if not batch_info or batch_info.get('is_shared', '0') != '1': return render_template('public_link_invalid.html', reason="Not shared."), 403
        batch_info['id'] = batch_id_str; batch_info['share_token'] = share_token
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1); js_media_list = []
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata and mdata.get('is_hidden','0')=='0' and mdata.get('processing_status','completed')=='completed' and mdata.get('item_type','media')=='media':
                rpath = mdata.get('filepath'); mimetype = mdata.get('mimetype')
                if rpath and mimetype and mimetype.startswith(('image/','video/','audio/')): js_media_list.append({'filepath':url_for('static',filename=f"uploads/{rpath.lstrip('/')}"),'mimetype':mimetype,'original_filename':mdata.get('original_filename','unknown')})
        if not js_media_list: flash("No playable items.", "info"); return redirect(url_for('public_batch_view', share_token=share_token))
        return render_template('slideshow.html', batch=batch_info, media_data_json=json.dumps(js_media_list), is_public_view=True)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error public_slideshow {share_token}: {e}"); return render_template('public_link_invalid.html', reason="DB error."), 500
    except Exception as e: app.logger.error(f"Error public_slideshow {share_token}: {e}", exc_info=True); return render_template('public_link_invalid.html', reason="Error."), 500

@app.route('/media/<uuid:media_id>/toggle_hidden', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media')
def toggle_hidden(media_id, media_data):
    if not redis_client: abort(503, description="DB unavailable.")
    media_id_str = str(media_id)
    if media_data.get('item_type','media') != 'media': flash("Action only for media.", "warning"); return redirect(url_for('collection_view', batch_id=media_data.get('batch_id')) if media_data.get('batch_id') else url_for('index'))
    try:
        new_status = '0' if media_data.get('is_hidden','0') == '1' else '1'; redis_client.hset(f'media:{media_id_str}','is_hidden',new_status)
        flash(f"Media '{media_data.get('original_filename',media_id_str)}' now {'visible' if new_status=='0' else 'hidden'}.", 'success')
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error toggle_hidden {media_id_str}: {e}"); flash("DB error.", "danger")
    except Exception as e: app.logger.error(f"Error toggle_hidden {media_id_str}: {e}", exc_info=True); flash("Error.", "danger")
    return redirect(url_for('collection_view', batch_id=media_data.get('batch_id')) if media_data.get('batch_id') else url_for('index'))

@app.route('/media/<uuid:media_id>/toggle_liked', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media')
def toggle_liked(media_id, media_data):
    if not redis_client: abort(503, description="DB unavailable.")
    media_id_str = str(media_id)
    if media_data.get('item_type','media') != 'media': flash("Action only for media.", "warning"); return redirect(url_for('collection_view', batch_id=media_data.get('batch_id')) if media_data.get('batch_id') else url_for('index'))
    try:
        new_status = '0' if media_data.get('is_liked','0') == '1' else '1'; redis_client.hset(f'media:{media_id_str}','is_liked',new_status)
        flash(f"Media '{media_data.get('original_filename',media_id_str)}' {'unliked' if new_status=='0' else 'liked'}.", 'success')
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error toggle_liked {media_id_str}: {e}"); flash("DB error.", "danger")
    except Exception as e: app.logger.error(f"Error toggle_liked {media_id_str}: {e}", exc_info=True); flash("Error.", "danger")
    return redirect(url_for('collection_view', batch_id=media_data.get('batch_id')) if media_data.get('batch_id') else url_for('index'))

@app.route('/media/<uuid:media_id>/delete', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media')
def delete_media(media_id, media_data):
    if not redis_client: abort(503, description="DB unavailable.")
    media_id_str = str(media_id); batch_id_redirect = media_data.get('batch_id'); orig_fname = media_data.get('original_filename',media_id_str); item_type = media_data.get('item_type','media')
    try:
        filepath_redis = media_data.get('filepath')
        if filepath_redis:
            disk_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filepath_redis)
            if os.path.isfile(disk_path):
                try: os.remove(disk_path); app.logger.info(f"Deleted file {disk_path} for item {media_id_str} (type: {item_type})")
                except OSError as e: app.logger.error(f"OS error deleting {disk_path}: {e}")
        pipe = redis_client.pipeline(); pipe.lrem(f'batch:{batch_id_redirect}:media_ids',0,media_id_str) if batch_id_redirect else None; pipe.delete(f'media:{media_id_str}')
        if item_type == 'archive_import' and batch_id_redirect: pipe.delete(f'batch_import_tracker:{batch_id_redirect}:{orig_fname}')
        pipe.execute(); flash(f"Item '{orig_fname}' deleted.", 'success')
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error deleting item {media_id_str}: {e}"); flash("DB error.", "danger")
    except Exception as e: app.logger.error(f"Error deleting item {media_id_str}: {e}", exc_info=True); flash("Error.", "danger")
    return redirect(url_for('collection_view', batch_id=batch_id_redirect) if batch_id_redirect else url_for('index'))

@app.route('/batch/<uuid:batch_id>/delete', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='batch')
def delete_batch(batch_id, batch_data):
    if not redis_client: abort(503, description="DB unavailable.")
    batch_id_str = str(batch_id); name_flash = batch_data.get('name',batch_id_str); owner_id = batch_data.get('user_id')
    try:
        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids',0,-1)
        pipe = redis_client.pipeline()
        if media_ids:
            for m_id in media_ids:
                m_info = redis_client.hgetall(f'media:{m_id}'); pipe.delete(f'media:{m_id}')
                if m_info.get('item_type')=='archive_import' and m_info.get('original_filename'): pipe.delete(f'batch_import_tracker:{batch_id_str}:{m_info.get("original_filename")}')
        pipe.delete(f'batch:{batch_id_str}:media_ids'); pipe.delete(f'batch:{batch_id_str}')
        if batch_data.get('share_token'): pipe.delete(f"share_token:{batch_data['share_token']}")
        if owner_id: pipe.lrem(f'user:{owner_id}:batches',0,batch_id_str)
        pipe.execute(); app.logger.info(f"Batch {batch_id_str} metadata deleted.")
        if owner_id:
            batch_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], owner_id, batch_id_str)
            if os.path.isdir(batch_dir):
                try: shutil.rmtree(batch_dir); app.logger.info(f"Deleted batch dir: {batch_dir}")
                except OSError as e: app.logger.error(f"OS error deleting dir {batch_dir}: {e}"); flash("Error deleting files.", "warning")
            else: app.logger.info(f"Batch dir not found: {batch_dir}")
        else: app.logger.error(f"No owner for batch dir {batch_id_str}."); flash("Could not delete files.", "warning")
        flash(f'Batch "{name_flash}" deleted.', 'success'); return redirect(url_for('index'))
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error deleting batch {batch_id_str}: {e}"); flash("DB error.", "danger")
    except Exception as e: app.logger.error(f"Error deleting batch {batch_id_str}: {e}", exc_info=True); flash("Error.", "danger")
    return redirect(url_for('index'))

@app.route('/batch/<uuid:batch_id>/export')
@login_required
@owner_or_admin_access_required(item_type='batch')
def export_batch(batch_id, batch_data):
    if not redis_client: abort(503, description="DB unavailable.")
    batch_id_str = str(batch_id); safe_name = secure_filename(batch_data.get('name',f'batch_{batch_id_str[:8]}')).replace(' ','_')
    manifest = {"lightbox_name": batch_data.get('name','Untitled'), "export_version": "1.1", "export_date": datetime.datetime.now(datetime.timezone.utc).isoformat(), "batch_id_exported_from": batch_id_str, "files": []}
    zip_fnames_used = set(); memory_zip = BytesIO(); files_in_zip = 0
    try:
        with zipfile.ZipFile(memory_zip,'w',zipfile.ZIP_DEFLATED) as zf:
            media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids',0,-1)
            if not media_ids: flash("Batch empty.", "info"); return redirect(url_for('collection_view', batch_id=batch_id_str))
            for idx, mid in enumerate(media_ids):
                minfo = redis_client.hgetall(f'media:{mid}')
                if minfo and minfo.get('is_hidden','0')=='0' and minfo.get('processing_status','completed')=='completed' and minfo.get('item_type') != 'archive_import':
                    rpath = minfo.get('filepath'); orig_fname = minfo.get('original_filename',f"item_{mid}"); item_type = minfo.get('item_type','media'); desc = minfo.get('description','')
                    if rpath:
                        dpath = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], rpath)
                        if os.path.isfile(dpath):
                            base, ext = os.path.splitext(orig_fname); arc_base = secure_filename(base if base else f"item_{idx}"); arc_cand = f"{arc_base}{ext if ext else '.bin'}"
                            ct = 0; final_arc = arc_cand
                            while final_arc in zip_fnames_used: ct+=1; final_arc = f"{arc_base}_{ct}{ext if ext else '.bin'}"
                            zip_fnames_used.add(final_arc); zf.write(dpath, arcname=final_arc)
                            manifest['files'].append({"zip_path":final_arc, "original_filename":orig_fname, "item_type":item_type, "mimetype":minfo.get('mimetype','application/octet-stream'), "description":desc, "is_hidden":minfo.get('is_hidden','0')=='1'})
                            files_in_zip +=1
                        else: app.logger.warning(f"Export: File missing {dpath}")
                    else: app.logger.warning(f"Export: Filepath missing for {mid}")
            if files_in_zip == 0: flash("No exportable files.", "warning"); return redirect(url_for('collection_view', batch_id=batch_id_str))
            zf.writestr('lightbox_manifest.json', json.dumps(manifest, indent=2))
        memory_zip.seek(0); zip_fname = f"LightBox_{safe_name}_Export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        app.logger.info(f"User '{session['username']}' exporting {files_in_zip} items from batch '{batch_id_str}'.")
        return send_file(memory_zip, mimetype='application/zip', as_attachment=True, download_name=zip_fname)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error export batch {batch_id_str}: {e}"); flash("DB error.", "danger")
    except Exception as e: app.logger.error(f"Error export batch {batch_id_str}: {e}", exc_info=True); flash("Error.", "danger")
    return redirect(url_for('collection_view', batch_id=batch_id_str))

@app.route('/batch/<string:batch_id>/rename', methods=['POST'])
@login_required
def rename_batch(batch_id):
    if not redis_client: return jsonify({'success': False, 'message': 'DB unavailable.'}), 503
    batch_id_str = str(batch_id)
    try: bdata = redis_client.hgetall(f'batch:{batch_id_str}')
    except redis.exceptions.RedisError as e: current_app.logger.error(f"Redis error batch {batch_id_str}: {e}"); return jsonify({'success':False,'message':'DB error.'}),500
    if not bdata: return jsonify({'success':False,'message':'Batch not found.'}),404
    owner = bdata.get('user_id')
    if not owner: return jsonify({'success':False,'message':'Batch data error.'}),500
    if owner != session.get('username') and not session.get('is_admin'): return jsonify({'success':False,'message':'Unauthorized.'}),403
    new_name = request.form.get('new_name','').strip()
    if not new_name: return jsonify({'success':False,'message':'Name empty.'}),400
    if len(new_name) > 255: return jsonify({'success':False,'message':'Name too long.'}),400
    old_name = bdata.get('name','Unnamed');
    if old_name == new_name: return jsonify({'success':True,'message':'Name unchanged.','new_name':new_name}),200
    try:
        pipe = redis_client.pipeline(); pipe.hset(f'batch:{batch_id_str}','name',new_name); pipe.hset(f'batch:{batch_id_str}','last_modified_timestamp',datetime.datetime.now().timestamp()); pipe.execute()
        current_app.logger.info(f"Batch '{old_name}' (ID: {batch_id_str}) renamed to '{new_name}' by {session.get('username')}")
        return jsonify({'success':True,'message':'Batch renamed.','new_name':new_name}),200
    except redis.exceptions.RedisError as e: current_app.logger.error(f"Redis rename error: {e}"); return jsonify({'success':False,'message':'DB error.'}),500
    except Exception as e: current_app.logger.error(f"Error renaming batch {batch_id_str}: {e}", exc_info=True); return jsonify({'success':False,'message':'Server error.'}),500

@app.route('/download_item/<uuid:batch_id>/<uuid:media_id>')
@login_required
@owner_or_admin_access_required(item_type='media')
def download_item(batch_id, media_id, media_data):
    if not redis_client: abort(503, description="DB unavailable.")
    rpath = media_data.get('filepath'); orig_fname = media_data.get('original_filename',f"download_{media_id}.bin"); mime = media_data.get('mimetype','application/octet-stream')
    if not rpath: app.logger.error(f"Download item {media_id} batch {batch_id} failed: No filepath."); flash("File info missing.", "danger"); return redirect(url_for('collection_view',batch_id=batch_id))
    dpath = os.path.join(app.root_path,app.config['UPLOAD_FOLDER'],rpath)
    if not os.path.isfile(dpath): app.logger.error(f"Download item {media_id} (path: {dpath}) failed: File not found."); flash("File not on server.", "danger"); return redirect(url_for('collection_view',batch_id=batch_id))
    app.logger.info(f"User '{session['username']}' downloading '{orig_fname}' (ID: {media_id})")
    try: return send_file(dpath, mimetype=mime, as_attachment=True, download_name=orig_fname)
    except Exception as e: app.logger.error(f"Error serving file {dpath}: {e}", exc_info=True); flash("Error preparing download.", "danger"); return redirect(url_for('collection_view',batch_id=batch_id))

@app.route('/public_download_item/<string:share_token>/<uuid:media_id>')
def public_download_item(share_token, media_id):
    if not redis_client: abort(503, description="DB unavailable.")
    try:
        batch_id_str = redis_client.get(f'share_token:{share_token}')
        if not batch_id_str: app.logger.warning(f"Public download: Invalid token: {share_token}"); abort(404)
        b_info = redis_client.hgetall(f'batch:{batch_id_str}')
        if not b_info or b_info.get('is_shared','0')!='1': app.logger.warning(f"Public download: Non-shared batch {batch_id_str}"); abort(403)
        mdata = redis_client.hgetall(f'media:{media_id}')
        if not mdata or mdata.get('batch_id')!=batch_id_str or mdata.get('is_hidden','0')=='1' or mdata.get('processing_status')!='completed' or mdata.get('item_type') not in ['media','blob']: app.logger.warning(f"Public download: Item {media_id} conditions not met."); abort(404)
        rpath = mdata.get('filepath'); orig_fname = mdata.get('original_filename',f"download_{media_id}.bin"); mime = mdata.get('mimetype','application/octet-stream')
        if not rpath: app.logger.error(f"Public download item {media_id} failed: No filepath."); abort(404)
        dpath = os.path.join(app.root_path,app.config['UPLOAD_FOLDER'],rpath)
        if not os.path.isfile(dpath): app.logger.error(f"Public download item {media_id} (path: {dpath}) failed: File not found."); abort(404)
        app.logger.info(f"Public download for '{orig_fname}' (ID: {media_id}) token {share_token}.")
        return send_file(dpath, mimetype=mime, as_attachment=True, download_name=orig_fname)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error public_download {share_token} media {media_id}: {e}"); abort(500)
    except Exception as e: app.logger.error(f"Error public_download {share_token} media {media_id}: {e}", exc_info=True); abort(500)

@app.route('/admin/users')
@login_required
@admin_required
def admin_dashboard():
    if not redis_client: flash("DB unavailable.", "danger"); return redirect(url_for('index'))
    try:
        usernames = redis_client.smembers('users'); users = []
        for uname in sorted(list(usernames),key=lambda s:s.lower()):
            uinfo = redis_client.hgetall(f'user:{uname}'); uinfo['username']=uname; uinfo['batch_count']=redis_client.llen(f'user:{uname}:batches'); users.append(uinfo)
        return render_template('admin_dashboard.html', users=users)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error admin_dashboard: {e}"); flash("Error loading admin data.", "danger"); return redirect(url_for('index'))

@app.route('/admin/change_password', methods=['POST'])
@login_required
@admin_required
def change_user_password():
    if not redis_client: flash("DB unavailable.", "danger"); return redirect(url_for('admin_dashboard'))
    target_user = request.form.get('username'); new_pass = request.form.get('new_password')
    if not target_user or not new_pass: flash('Username and new password required.', 'danger'); return redirect(url_for('admin_dashboard'))
    if len(new_pass) < 8: flash('Password too short (min 8 chars).', 'danger'); return redirect(url_for('admin_dashboard'))
    try:
        if not redis_client.sismember('users', target_user): flash(f'User "{target_user}" not found.', 'danger'); return redirect(url_for('admin_dashboard'))
        redis_client.hset(f'user:{target_user}','password_hash',generate_password_hash(new_pass))
        flash(f'Password updated for user "{target_user}".', 'success'); app.logger.info(f"Admin '{session['username']}' changed password for '{target_user}'.")
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error changing password for {target_user}: {e}"); flash("DB error.", "danger")
    return redirect(url_for('admin_dashboard'))

@app.errorhandler(400)
def bad_request_error(e):
    desc = getattr(e,'description',"Bad request."); title="400 - Bad Request"; app.logger.warning(f"HTML 400 {request.url}: {desc}", exc_info=e if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html: app.logger.warning(f"JSON 400 {request.url}: {desc}"); return jsonify(error="Bad Request",message=desc),400
    return render_template('400.html',error_title=title,error_message=desc),400
@app.errorhandler(401)
def unauthorized_error(e):
    desc = getattr(e,'description',"Unauthorized."); title="401 - Unauthorized"; app.logger.info(f"HTML 401 {request.url}: {desc}")
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html: app.logger.info(f"JSON 401 {request.url}: {desc}"); return jsonify(error="Unauthorized",message=desc),401
    return render_template('401.html',error_title=title,error_message=desc),401
@app.errorhandler(403)
def forbidden_error(e):
    desc = getattr(e,'description',"Forbidden."); title="403 - Forbidden"; app.logger.warning(f"HTML 403 {request.url}: {desc}", exc_info=e if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html: app.logger.warning(f"JSON 403 {request.url}: {desc}"); return jsonify(error="Forbidden",message=desc),403
    return render_template('403.html',error_title=title,error_message=desc),403
@app.errorhandler(404)
def page_not_found_error(e):
    desc = getattr(e,'description',"Page not found."); title="404 - Page Not Found"; app.logger.warning(f"HTML 404 {request.url}: {desc}", exc_info=e if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html: app.logger.warning(f"JSON 404 {request.url}: {desc}"); return jsonify(error="Not Found",message=desc),404
    return render_template('404.html',error_title=title,error_message=desc),404
@app.errorhandler(413)
def request_entity_too_large_error(e):
    max_bytes = app.config.get('MAX_CONTENT_LENGTH',0); max_read = "limit"
    if max_bytes > 0:
        gb,mb,kb = 1024**3,1024**2,1024
        if max_bytes>=gb: max_read=f"{max_bytes/gb:.1f} GB"
        elif max_bytes>=mb: max_read=f"{max_bytes/mb:.0f} MB"
        else: max_read=f"{max_bytes/kb:.0f} KB"
    msg = f"Upload failed: File(s) too large. Max allowed: {max_read}."; title="413 - Payload Too Large"; app.logger.warning(f"413 {request.url}. {msg}")
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html: return jsonify(error="Payload Too Large",message=msg,limit=max_read),413
    flash(msg,"danger");
    if request.referrer and request.referrer != request.url: return redirect(request.referrer)
    return render_template('413.html',error_title=title,error_message=msg,max_upload_size=max_read),413
@app.errorhandler(429)
def too_many_requests_error(e):
    desc = getattr(e,'description',"Too many requests."); title="429 - Too Many Requests"; app.logger.warning(f"HTML 429 {request.url}: {desc}", exc_info=e if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html: headers=getattr(e,'headers',{}); return jsonify(error="Too Many Requests",message=desc),429,headers
    return render_template('429.html',error_title=title,error_message=desc),429
@app.errorhandler(500)
def internal_server_error(e):
    orig_exc = str(getattr(e,'original_exception',e)); title="500 - Server Error"; msg_template="Server error. Try again or contact support."
    app.logger.error(f"500 {request.url}: {orig_exc}", exc_info=True)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html: return jsonify(error="Internal Server Error",message="Server error."),500
    return render_template('500.html',error_title=title,error_message=msg_template),500
@app.errorhandler(503)
def service_unavailable_error(e):
    desc = getattr(e,'description',"Service unavailable."); title="503 - Service Unavailable"; app.logger.error(f"503 {request.url}: {desc}", exc_info=True if app.debug else False)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html: headers=getattr(e,'headers',{}); return jsonify(error="Service Unavailable",message=desc),503,headers
    return render_template('503.html',error_title=title,error_message=desc),503

if __name__ == '__main__':
    print("--- Starting Flask App (local dev/test) ---")
    upload_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    if not os.path.exists(upload_dir):
        try: os.makedirs(upload_dir); print(f"Created UPLOAD_FOLDER: {upload_dir}")
        except OSError as e: print(f"ERROR creating UPLOAD_FOLDER {upload_dir}: {e}")
    app.logger.info(f"App '{app.name}' mode '{app.env}' (debug={app.debug}).")
    # ... (other startup logs from your original) ...
    app.logger.info(f"FFMPEG_PATH used by app: {app.config.get('FFMPEG_PATH')}")
    app.logger.info(f"APP_REDIS_DB_NUM for app data: {app.config.get('APP_REDIS_DB_NUM')}")
    app.logger.info(f"Celery Broker URL: {app.config.get('broker_url')}")
    app.logger.info(f"Celery Result Backend URL: {app.config.get('result_backend')}")
    app.logger.info(f"Video to MP4 Config: Formats='{app.config.get('VIDEO_FORMATS_TO_CONVERT_TO_MP4')}'")
    app.logger.info(f"Audio to MP3 Config: Formats='{app.config.get('AUDIO_FORMATS_TO_CONVERT_TO_MP3')}'")
    
    host = os.environ.get('FLASK_RUN_HOST','0.0.0.0'); port = int(os.environ.get('FLASK_RUN_PORT',5102))
    app.run(debug=app.debug, host=host, port=port)
