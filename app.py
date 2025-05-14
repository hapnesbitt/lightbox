import datetime
import os
import uuid # Ensure uuid is imported
import json
import shutil
import zipfile
from functools import wraps
from io import BytesIO
import logging
import secrets
import subprocess # For FFmpeg

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort, jsonify, current_app 
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import redis
from urllib.parse import urlparse as url_parse
from celery import Celery # Import Celery

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a-very-strong-dev-secret-key-please-change!')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 9000 * 1024 * 1024  # 9GB
app.config['FFMPEG_PATH'] = os.environ.get('FFMPEG_PATH', 'ffmpeg') 

# --- Celery Configuration ---
redis_password_for_celery = os.environ.get('REDIS_PASSWORD', 'simplenes')
redis_host_for_celery = os.environ.get('REDIS_HOST', 'localhost')
redis_port_for_celery = os.environ.get('REDIS_PORT', 6379)
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
    celery_instance.conf.broker_url = flask_app.config['broker_url']
    celery_instance.conf.result_backend = flask_app.config['result_backend']
    celery_instance.conf.task_track_started = flask_app.config.get('task_track_started', True)
    class ContextTask(celery_instance.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)
    celery_instance.Task = ContextTask
    return celery_instance
celery = make_celery(app)

# --- Logging Setup ---
if not app.debug:
    if not app.logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        app.logger.addHandler(stream_handler)
    app.logger.setLevel(logging.INFO)
else:
    app.logger.setLevel(logging.DEBUG)

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.datetime.now().year}

csrf = CSRFProtect(app)

# --- Redis Connection ---
try:
    redis_client = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        password=os.environ.get('REDIS_PASSWORD', 'simplenes'), 
        decode_responses=True,
        socket_connect_timeout=5
    )
    redis_client.ping()
    app.logger.info("Successfully connected to Redis.")
except Exception as e:
    app.logger.error(f"FATAL: Could not connect to Redis: {e}. Application may not function correctly.")
    redis_client = None 

# --- Jinja Filters ---
def timestamp_to_date_filter(timestamp_str):
    if not timestamp_str: return "N/A"
    try:
        dt_object = datetime.datetime.fromtimestamp(float(timestamp_str))
        return dt_object.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError) as e:
        app.logger.debug(f"Error converting timestamp '{timestamp_str}': {e}")
        return "Invalid Date"
app.jinja_env.filters['timestamp_to_date'] = timestamp_to_date_filter

# --- Allowed File Extensions ---
ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'svg', 'avif', 'bmp', 'ico',
    'mp4', 'mkv', 'mov', 'webm', 'ogv', '3gp', '3g2', 
    'mp3', 'aac', 'wav', 'ogg', 'opus', 'flac', 'm4a', 'pdf'
}
MIME_TYPE_MAP = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.gif': 'image/gif', '.webp': 'image/webp', '.heic': 'image/heic',
    '.heif': 'image/heif', '.svg': 'image/svg+xml', '.avif': 'image/avif',
    '.bmp': 'image/bmp', '.ico': 'image/x-icon', '.mp4': 'video/mp4',
    '.mov': 'video/quicktime', '.mkv': 'video/x-matroska', '.webm': 'video/webm',
    '.ogv': 'video/ogg', '.3gp': 'video/3gpp', '.3g2': 'video/3gpp2',
    '.mp3': 'audio/mpeg', '.aac': 'audio/aac', '.wav': 'audio/wav',
    '.ogg': 'audio/ogg', '.opus': 'audio/opus', '.flac': 'audio/flac',
    '.m4a': 'audio/mp4', '.pdf': 'application/pdf'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Initial Admin User Setup ---
if redis_client:
    try:
        if not redis_client.sismember('users', 'admin'):
            admin_password = os.environ.get('LIGHTBOX_ADMIN_PASSWORD', 'ChangeThisDefaultAdminPassw0rd!')
            if admin_password == 'ChangeThisDefaultAdminPassw0rd!':
                 app.logger.warning("Using default admin password. SET LIGHTBOX_ADMIN_PASSWORD ENV VAR.")
            redis_client.sadd('users', 'admin')
            redis_client.hset('user:admin', mapping={
                'password_hash': generate_password_hash(admin_password), 'is_admin': '1'
            })
            app.logger.info("Admin user 'admin' created/verified.")
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error during admin user setup: {e}")
else:
    app.logger.warning("Redis not connected. Admin user setup skipped.")

# --- Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in.', 'warning')
            return redirect(url_for('login', next=request.url))
        if not session.get('is_admin'):
            flash('Admin privileges required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def owner_or_admin_access_required(item_type='batch'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                flash('Please log in.', 'warning')
                return redirect(url_for('login', next=request.url))
            if not redis_client: abort(503, description="Database service unavailable.")
            
            item_id_to_check = kwargs.get(f'{item_type}_id')
            if not item_id_to_check:
                app.logger.error(f"Ownership check: No ID for '{item_type}'. Kwargs: {kwargs}")
                flash('Cannot verify ownership: Item ID missing.', 'danger')
                return redirect(url_for('index'))

            item_id_to_check_str = str(item_id_to_check) 

            item_data_key = f'{item_type}:{item_id_to_check_str}'
            item_data = redis_client.hgetall(item_data_key)
            
            if not item_data:
                flash(f'{item_type.capitalize()} not found.', 'warning')
                return redirect(url_for('index'))
            
            owner_field = 'uploader_user_id' if item_type == 'media' else 'user_id'
            item_owner_username = item_data.get(owner_field)

            if not item_owner_username: 
                 app.logger.error(f"Ownership check: Owner field '{owner_field}' missing for {item_data_key}")
                 flash('Cannot verify ownership: Item data incomplete.', 'danger')
                 return redirect(url_for('index'))

            if item_owner_username != session['username'] and not session.get('is_admin'):
                flash(f'You do not have permission to access this {item_type}.', 'danger')
                return redirect(url_for('index'))
            
            item_data['id_str_for_template'] = item_id_to_check_str 
            kwargs[f'{item_type}_data'] = item_data
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# In app.py

# ... (other code) ...

# --- Celery Task for MKV Conversion ---
@celery.task(bind=True, name='app.convert_mkv_to_mp4_task', max_retries=3, default_retry_delay=60)
def convert_mkv_to_mp4_task(self, original_mkv_temp_path, target_mp4_disk_path, 
                            media_id_for_update, batch_id_for_update,
                            original_filename_for_log, disk_path_segment_for_batch,
                            uploader_username_for_log):
    # All code for this task must be indented under this function definition
    task_id = self.request.id
    logger = current_app.logger 
    logger.info(f"[Celery Task {task_id}] User: {uploader_username_for_log} - Starting MKV Transcode: {original_filename_for_log} (media: {media_id_for_update})")
    logger.debug(f"[Celery Task {task_id}] Input: {original_mkv_temp_path}, Output: {target_mp4_disk_path}")
    
    # ffmpeg_path must be defined INSIDE the function, before ffmpeg_command uses it
    ffmpeg_path = current_app.config.get('FFMPEG_PATH', 'ffmpeg')

    # The ffmpeg_command list must be INSIDE the function
    ffmpeg_command = [
        ffmpeg_path,
        '-i', original_mkv_temp_path,
        '-c:v', 'libx264',         # Transcode video to H.264
        '-preset', 'fast',         # Encoding speed/compression balance
        '-crf', '23',              # Quality (lower is better, 18-28 good range)
        '-c:a', 'aac',             # Attempt to transcode audio to AAC
        '-b:a', '128k',            # Audio bitrate
        '-movflags', '+faststart', # For web streaming
        '-y',                      # Overwrite output without asking
        target_mp4_disk_path
    ] # Only ONE closing bracket for the list

    # This must be INSIDE the function
    processing_status_update = {
        'processing_status': 'failed', 
        'error_message': 'Unknown conversion error. Task did not complete as expected.'
    }
    
    # This try block must be INSIDE the function
    try:
        logger.info(f"[Celery Task {task_id}] Executing FFmpeg (transcoding): {' '.join(ffmpeg_command)}")
        process = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, timeout=3600)
        
        logger.info(f"[Celery Task {task_id}] FFmpeg transcode success for {original_filename_for_log}.")
        if process.stdout: logger.debug(f"FFmpeg stdout: {process.stdout.strip()}")
        if process.stderr: logger.info(f"FFmpeg stderr (on success): {process.stderr.strip()}")

        final_output_mp4_disk_filename = os.path.basename(target_mp4_disk_path)
        final_redis_filepath_mp4 = os.path.join(disk_path_segment_for_batch, final_output_mp4_disk_filename)
        
        processing_status_update = {
            'filename_on_disk': final_output_mp4_disk_filename,
            'filepath': final_redis_filepath_mp4,
            'mimetype': 'video/mp4',
            'processing_status': 'completed',
            'error_message': '' 
        }
        logger.info(f"[Celery Task {task_id}] Prepared successful update for media {media_id_for_update} after transcoding: {processing_status_update}")
        
        task_redis_client = redis.Redis(
            host=current_app.config.get('REDIS_HOST', os.environ.get('REDIS_HOST', 'localhost')),
            port=int(current_app.config.get('REDIS_PORT', os.environ.get('REDIS_PORT', 6379))),
            password=current_app.config.get('REDIS_PASSWORD', os.environ.get('REDIS_PASSWORD', None)),
            decode_responses=True, socket_connect_timeout=5 )
        task_redis_client.hmset(f'media:{media_id_for_update}', processing_status_update)
        logger.info(f"[Celery Task {task_id}] Redis updated successfully for media {media_id_for_update} with transcoded MP4 details.")

        return {'status': 'success', 'output_path': target_mp4_disk_path, 'media_id': media_id_for_update}

    except subprocess.CalledProcessError as e_ffmpeg:
        logger.error(f"[Celery Task {task_id}] FFmpeg TRANSCODE FAILED for {original_filename_for_log} (rc {e_ffmpeg.returncode}):")
        if e_ffmpeg.stdout: logger.error(f"FFmpeg stdout: {e_ffmpeg.stdout.strip()}")
        if e_ffmpeg.stderr: logger.error(f"FFmpeg stderr: {e_ffmpeg.stderr.strip()}")
        processing_status_update.update({'error_message': f'FFmpeg transcoding error (rc {e_ffmpeg.returncode}).'})
        if hasattr(self, 'retry') and self.request.retries < self.max_retries :
            logger.info(f"[Celery Task {task_id}] Retrying FFmpeg FAILED TRANSCODE task for {original_filename_for_log}...")
            raise self.retry(exc=e_ffmpeg, countdown=int(getattr(self, 'default_retry_delay', 60) * (self.request.retries + 1)**2))
        else:
            logger.error(f"[Celery Task {task_id}] Max retries reached for FFmpeg FAILED TRANSCODE task {original_filename_for_log}.")
            raise 
    except subprocess.TimeoutExpired as e_timeout:
        logger.error(f"[Celery Task {task_id}] FFmpeg TRANSCODE timeout for {original_filename_for_log}.")
        processing_status_update.update({'error_message': 'FFmpeg transcoding timeout.'})
        if hasattr(self, 'retry') and self.request.retries < self.max_retries:
            logger.info(f"[Celery Task {task_id}] Retrying FFmpeg TRANSCODE TIMEOUT task for {original_filename_for_log}...")
            raise self.retry(exc=e_timeout, countdown=int(getattr(self, 'default_retry_delay', 60) * (self.request.retries + 1)**2))
        else:
            logger.error(f"[Celery Task {task_id}] Max retries reached for FFmpeg TRANSCODE TIMEOUT task {original_filename_for_log}.")
            raise
    except Exception as e:
        logger.error(f"[Celery Task {task_id}] Unexpected error during TRANSCODE for {original_filename_for_log}: {e}", exc_info=True)
        processing_status_update.update({'error_message': f'Unexpected transcoding error: {str(e)[:100]}'})
        raise 
    finally:
        final_update_redis_client = redis.Redis(
            host=current_app.config.get('REDIS_HOST', os.environ.get('REDIS_HOST', 'localhost')),
            port=int(current_app.config.get('REDIS_PORT', os.environ.get('REDIS_PORT', 6379))),
            password=current_app.config.get('REDIS_PASSWORD', os.environ.get('REDIS_PASSWORD', None)),
            decode_responses=True, socket_connect_timeout=5 )
        try:
            if 'processing_status' in processing_status_update:
                 final_update_redis_client.hmset(f'media:{media_id_for_update}', processing_status_update)
                 logger.info(f"[Celery Task {task_id}] Final Redis status after TRANSCODE attempt for media {media_id_for_update}: {processing_status_update.get('processing_status')}")
            else: 
                 logger.warning(f"[Celery Task {task_id}] processing_status_update was not set for media {media_id_for_update} in finally block after TRANSCODE attempt.")
        except Exception as redis_e_final:
            logger.error(f"[Celery Task {task_id}] CRITICAL: Failed Redis update in finally for media {media_id_for_update} after TRANSCODE attempt: {redis_e_final}")
        
        if os.path.exists(original_mkv_temp_path):
            try:
                os.remove(original_mkv_temp_path)
                logger.info(f"[Celery Task {task_id}] Cleaned temp MKV after TRANSCODE attempt: {original_mkv_temp_path}")
            except OSError as e_rm:
                logger.error(f"[Celery Task {task_id}] Error removing temp MKV {original_mkv_temp_path} after TRANSCODE attempt: {e_rm}")

# --- Routes ---
@app.route('/')
@app.route('/index')
@login_required
def index():
    # ... (Unchanged from your file) ...
    if not redis_client:
        flash('Database service unavailable. Please try again later.', 'danger')
        return render_template('index.html', batches=[])
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
                    if m_status == 'completed' or m_status is None: 
                        completed_media_count += 1
                batch_info['item_count'] = completed_media_count
                batches_data.append(batch_info)
        batches_data.sort(key=lambda x: float(x.get('creation_timestamp', 0)), reverse=True)
        return render_template('index.html', batches=batches_data)
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error for user {username} on index: {e}")
        flash('Error retrieving your lightboxes. Please try again.', 'danger')
        return render_template('index.html', batches=[])

@app.route('/register', methods=['GET', 'POST'])
def register():
    # ... (Unchanged from your file) ...
    if request.method == 'POST':
        if not redis_client: 
            flash('Registration service temporarily unavailable. Please try again later.', 'danger')
            return render_template('register.html')
        username = request.form.get('username','').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not username or not password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('register.html')
        if len(username) < 3:
            flash('Username must be at least 3 characters long.', 'danger')
            return render_template('register.html')
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')
        if len(password) < 6: 
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('register.html')
        try:
            if redis_client.sismember('users', username):
                flash('Username already exists. Please choose a different one.', 'danger')
                return render_template('register.html')
            redis_client.sadd('users', username)
            redis_client.hset(f'user:{username}', mapping={
                'password_hash': generate_password_hash(password), 
                'is_admin': '0' 
            })
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
        except redis.exceptions.RedisError as e:
            app.logger.error(f"Redis error during registration for {username}: {e}")
            flash('An error occurred during registration. Please try again.', 'danger')
            return render_template('register.html')
    return render_template('register.html')

@app.route('/about')
@login_required # This ensures only logged-in users can access the about page
def about_page():
    current_app.logger.info(f"Serving /about page for user: {session.get('username', 'Guest')}") # Optional: for logging
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # ... (Unchanged from your file) ...
    if request.method == 'POST':
        if not redis_client:
            flash('Login service temporarily unavailable. Please try again later.', 'danger')
            return render_template('login.html')
        username = request.form.get('username')
        password = request.form.get('password')
        try:
            if not redis_client.sismember('users', username):
                flash('Invalid username or password.', 'danger')
                return render_template('login.html')
            user_data = redis_client.hgetall(f'user:{username}')
            if not user_data.get('password_hash') or not check_password_hash(user_data['password_hash'], password):
                flash('Invalid username or password.', 'danger')
                return render_template('login.html')
            session['username'] = username
            session['is_admin'] = user_data.get('is_admin') == '1'
            flash(f'Welcome back, {username}!', 'success')
            next_url = request.args.get('next')
            if next_url and url_parse(next_url).netloc == '':
                return redirect(next_url)
            return redirect(url_for('index'))
        except redis.exceptions.RedisError as e:
            app.logger.error(f"Redis error during login for {username}: {e}")
            flash('An error occurred during login. Please try again.', 'danger')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    # ... (Unchanged from your file) ...
    session.clear()
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    # ... (Unchanged from your file - this is the version with Celery dispatch for MKV) ...
    if not redis_client:
        flash('Database service unavailable. Cannot process upload.', 'danger')
        return redirect(request.referrer or url_for('index'))
    if 'files[]' not in request.files:
        flash('No file part in the form. Please select files.', 'danger')
        return redirect(request.referrer or url_for('index'))
    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files):
        flash('No files selected for upload.', 'danger')
        return redirect(request.referrer or url_for('index'))
    current_user_username = session['username']
    existing_batch_id_from_form = request.form.get('existing_batch_id')
    batch_id_to_use_str = None 
    batch_name_to_use = "" 
    is_new_batch = True
    batch_owner_username = current_user_username 
    if existing_batch_id_from_form:
        is_new_batch = False; batch_id_to_use_str = existing_batch_id_from_form
        try:
            batch_info_existing = redis_client.hgetall(f'batch:{batch_id_to_use_str}')
            if not batch_info_existing: flash(f'Selected batch (ID: {batch_id_to_use_str}) not found.', 'danger'); return redirect(request.referrer or url_for('index'))
            batch_owner_username = batch_info_existing.get('user_id')
            if not batch_owner_username: app.logger.error(f"Batch {batch_id_to_use_str} is missing 'user_id'."); flash('Selected batch has inconsistent data.', 'danger'); return redirect(request.referrer or url_for('index'))
            if batch_owner_username != current_user_username and not session.get('is_admin'): flash('You do not have permission to add files to this batch.', 'danger'); return redirect(request.referrer or url_for('index'))
            batch_name_to_use = batch_info_existing.get('name', f'Batch_{batch_id_to_use_str[:8]}')
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error checking batch {batch_id_to_use_str}: {e}"); flash("DB error verifying batch.", "danger"); return redirect(request.referrer or url_for('index'))
    else:
        is_new_batch = True; batch_name_from_form = request.form.get('batch_name', '').strip()
        if not batch_name_from_form: flash('A name is required for new batch.', 'warning'); return redirect(request.referrer or url_for('index'))
        batch_id_to_use_str = str(uuid.uuid4()); batch_name_to_use = batch_name_from_form
    disk_path_segment_for_batch = os.path.join(batch_owner_username, batch_id_to_use_str)
    full_disk_upload_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], disk_path_segment_for_batch)
    try: os.makedirs(full_disk_upload_dir, exist_ok=True)
    except OSError as e: app.logger.error(f"Error creating dir '{full_disk_upload_dir}': {e}"); flash("Server error creating upload dir.", "danger"); return redirect(request.referrer or url_for('index'))
    files_uploaded_or_queued_count = 0; redis_pipeline = redis_client.pipeline(); mkv_files_were_queued = False 
    for file_item in files:
        if not file_item or not file_item.filename: continue
        original_filename = file_item.filename
        if allowed_file(original_filename):
            base, ext_with_dot = os.path.splitext(original_filename); ext_lower = ext_with_dot.lower(); media_id = str(uuid.uuid4()) 
            if ext_lower == '.mkv':
                mkv_files_were_queued = True; app.logger.info(f"User '{current_user_username}' - MKV: {original_filename}. Queuing (media_id: {media_id}).")
                temp_mkv_input_filename = f"{media_id}_celery_input.mkv"; temp_mkv_input_path = os.path.join(full_disk_upload_dir, temp_mkv_input_filename)
                secure_base_for_output_mp4 = secure_filename(base) if base else "video"; final_output_mp4_disk_filename_base = f"{secure_base_for_output_mp4}.mp4"
                counter = 1; target_mp4_disk_filename_final = final_output_mp4_disk_filename_base; target_mp4_disk_path = os.path.join(full_disk_upload_dir, target_mp4_disk_filename_final)
                while os.path.exists(target_mp4_disk_path): target_mp4_disk_filename_final = f"{secure_base_for_output_mp4}_{counter}.mp4"; target_mp4_disk_path = os.path.join(full_disk_upload_dir, target_mp4_disk_filename_final); counter += 1
                try:
                    file_item.save(temp_mkv_input_path)
                    initial_redis_filepath = os.path.join(disk_path_segment_for_batch, temp_mkv_input_filename)
                    redis_pipeline.hset(f'media:{media_id}', mapping={
                        'original_filename': original_filename, 'filename_on_disk': temp_mkv_input_filename, 'filepath': initial_redis_filepath, 
                        'mimetype': MIME_TYPE_MAP.get('.mkv', 'video/x-matroska'), 'is_hidden': '0', 'is_liked': '0', 
                        'uploader_user_id': current_user_username, 'batch_id': batch_id_to_use_str, 
                        'upload_timestamp': datetime.datetime.now().timestamp(), 'processing_status': 'queued' })
                    redis_pipeline.rpush(f'batch:{batch_id_to_use_str}:media_ids', media_id)
                    convert_mkv_to_mp4_task.apply_async(args=[ temp_mkv_input_path, target_mp4_disk_path, media_id, batch_id_to_use_str, original_filename, disk_path_segment_for_batch, current_user_username])
                    app.logger.info(f"MKV '{original_filename}' (media_id: {media_id}) queued. Target MP4: {target_mp4_disk_path}"); files_uploaded_or_queued_count += 1
                except Exception as e_queue: 
                    app.logger.error(f"Error saving/queuing MKV '{original_filename}': {e_queue}", exc_info=True); flash(f"Error preparing MKV '{original_filename}'. Skipped.", "danger")
                    if os.path.exists(temp_mkv_input_path): 
                        try: os.remove(temp_mkv_input_path)
                        except OSError as e_rm_cleanup: app.logger.error(f"Error cleaning up temp MKV {temp_mkv_input_path} after queue fail: {e_rm_cleanup}") 
            else: 
                secure_base_orig = secure_filename(base) if base else "file" ; disk_filename_orig_base = f"{secure_base_orig}{ext_lower}"
                counter_orig = 1; final_disk_filename_on_server = disk_filename_orig_base; disk_filepath_to_save_to = os.path.join(full_disk_upload_dir, final_disk_filename_on_server)
                while os.path.exists(disk_filepath_to_save_to): final_disk_filename_on_server = f"{secure_base_orig}_{counter_orig}{ext_lower}"; disk_filepath_to_save_to = os.path.join(full_disk_upload_dir, final_disk_filename_on_server); counter_orig += 1
                try:
                    file_item.save(disk_filepath_to_save_to); final_redis_filepath = os.path.join(disk_path_segment_for_batch, final_disk_filename_on_server); final_mimetype = MIME_TYPE_MAP.get(ext_lower, 'application/octet-stream')
                    redis_pipeline.hset(f'media:{media_id}', mapping={
                        'original_filename': original_filename, 'filename_on_disk': final_disk_filename_on_server, 'filepath': final_redis_filepath, 
                        'mimetype': final_mimetype, 'is_hidden': '0', 'is_liked': '0', 'uploader_user_id': current_user_username, 
                        'batch_id': batch_id_to_use_str, 'upload_timestamp': datetime.datetime.now().timestamp(), 'processing_status': 'completed' })
                    redis_pipeline.rpush(f'batch:{batch_id_to_use_str}:media_ids', media_id); files_uploaded_or_queued_count += 1
                except Exception as e_save: app.logger.error(f"Error saving '{original_filename}' to '{disk_filepath_to_save_to}': {e_save}"); flash(f"Error saving file '{original_filename}'. Skipped.", "danger")
        elif original_filename: flash(f'File type of "{original_filename}" not allowed. Skipped.', 'warning')
    try: redis_pipeline.execute() 
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis pipeline error for batch {batch_id_to_use_str}: {e}"); flash("DB error saving media. Upload incomplete.", "danger"); return redirect(request.referrer or url_for('index'))
    if files_uploaded_or_queued_count > 0:
        try:
            if is_new_batch:
                redis_client.hset(f'batch:{batch_id_to_use_str}', mapping={
                    'user_id': batch_owner_username, 'creation_timestamp': datetime.datetime.now().timestamp(),
                    'name': batch_name_to_use, 'is_shared': '0', 'share_token': ''  })
                redis_client.lpush(f'user:{batch_owner_username}:batches', batch_id_to_use_str)
            else: redis_client.hset(f'batch:{batch_id_to_use_str}', 'last_modified_timestamp', datetime.datetime.now().timestamp())
            flash_msg = f'{files_uploaded_or_queued_count} file(s) submitted for batch "{batch_name_to_use}".'; 
            if mkv_files_were_queued: flash_msg += " MKV files are processing and will appear when ready."
            flash(flash_msg.strip(), 'success'); return redirect(url_for('collection_view', batch_id=batch_id_to_use_str))
        except redis.exceptions.RedisError as e: app.logger.error(f"Redis error finalizing batch {batch_id_to_use_str}: {e}"); flash("Files processed, but error saving batch details.", "warning"); return redirect(url_for('index'))
    else: 
        if is_new_batch and os.path.exists(full_disk_upload_dir) and not os.listdir(full_disk_upload_dir):
            try: shutil.rmtree(full_disk_upload_dir); app.logger.info(f"Removed empty new batch dir: {full_disk_upload_dir}")
            except OSError as e_rm: app.logger.error(f"Error removing empty dir '{full_disk_upload_dir}': {e_rm}")
        flash('No valid files uploaded/processed. Check types/selection.', 'danger'); return redirect(request.referrer or url_for('index'))


@app.route('/batch/<uuid:batch_id>')
@login_required
@owner_or_admin_access_required(item_type='batch') 
def collection_view(batch_id, batch_data): 
    if not redis_client: 
        flash('Database service unavailable.', 'danger')
        return redirect(url_for('index'))
    try:
        batch_info = batch_data 
        batch_id_str = str(batch_id)
        batch_info['id'] = batch_id_str
        # batch_info['id_type_str_debug'] = str(type(batch_info.get('id'))) # Debug line, can be removed
        # app.logger.info(f"For collection.html, batch_info['id'] is: '{batch_info.get('id')}', type from Python: {batch_info.get('id_type_str_debug')}") 

        batch_info['is_shared_val'] = batch_info.get('is_shared', '0')
        batch_info['share_token_val'] = batch_info.get('share_token', '')
        if batch_info.get('is_shared') == '1' and batch_info.get('share_token'):
            batch_info['public_share_url'] = url_for('public_batch_view', share_token=batch_info['share_token_val'], _external=True)

        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1) 
        media_list = []
        valid_items_count = 0
        is_any_item_processing_flag = False # New flag for auto-refresh

        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            # app.logger.debug(f"COLLECTION_VIEW - Raw Redis Data for media_id {mid}: {mdata}") # Optional: keep for detailed debugging
            if mdata:
                mdata['id'] = mid
                current_status = mdata.get('processing_status', 'completed')
                mdata['processing_status'] = current_status
                mdata['error_message'] = mdata.get('error_message', '')
                
                if current_status not in ['completed', 'failed']:
                    is_any_item_processing_flag = True
                
                rpath = mdata.get('filepath') 
                if rpath: 
                    mdata['web_path'] = url_for('static', filename=f"uploads/{rpath.lstrip('/')}")
                else: 
                    mdata['web_path'] = None 
                    if current_status == 'completed': 
                        app.logger.warning(f"Collection View: Completed media item {mid} in batch {batch_id_str} is missing its filepath in Redis.")
                
                media_list.append(mdata)
                if current_status == 'completed':
                    valid_items_count +=1 
        
        batch_info['item_count'] = valid_items_count 
        
        app.logger.info(f"Collection View for {batch_id_str}: is_any_item_processing={is_any_item_processing_flag}")
        return render_template('collection.html', 
                               batch=batch_info, 
                               media_items=media_list,
                               is_any_item_processing=is_any_item_processing_flag) # Pass flag to template
    except redis.exceptions.RedisError as e: 
        app.logger.error(f"Redis error in collection_view for batch {str(batch_id)}: {e}")
        flash("Error loading batch details.", 'danger')
        return redirect(url_for('index'))
    except Exception as e: 
        app.logger.error(f"Unexpected error in collection_view for {str(batch_id)}: {e}", exc_info=True)
        flash("Error loading collection.", "danger")
        return redirect(url_for('index'))

@app.route('/slideshow/<uuid:batch_id>') 
@login_required
@owner_or_admin_access_required(item_type='batch') 
def slideshow(batch_id, batch_data): 
    if not redis_client: flash('DB unavailable.', 'danger'); return redirect(url_for('index'))
    try:
        batch_info = batch_data
        batch_id_str = str(batch_id)
        batch_info['id'] = batch_id_str
        app.logger.info(f"--- Preparing slideshow for batch {batch_id_str} ---")

        media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1) 
        app.logger.debug(f"SLIDESHOW_VIEW - Raw media_ids from Redis for batch {batch_id_str}: {media_ids}")
        js_media_list = []
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            app.logger.debug(f"SLIDESHOW_VIEW - Raw Redis Data for media_id {mid}: {mdata}")
            
            processing_status = mdata.get('processing_status', 'completed')
            is_hidden = mdata.get('is_hidden', '0') == '1'
            mimetype = mdata.get('mimetype')
            rpath = mdata.get('filepath')

            app.logger.debug(f"SLIDESHOW_VIEW - Evaluating media_id {mid}: Status='{processing_status}', Hidden='{is_hidden}', Mimetype='{mimetype}', Filepath='{rpath}'")

            if mdata and not is_hidden and processing_status == 'completed': 
                if rpath and mimetype and mimetype.startswith(('image/', 'video/', 'audio/')):
                    web_path = url_for('static', filename=f"uploads/{rpath.lstrip('/')}")
                    js_media_list.append({'filepath': web_path, 'mimetype': mimetype, 'original_filename': mdata.get('original_filename', 'unknown_file') })
                    app.logger.debug(f"SLIDESHOW_VIEW - ADDED to js_media_list: {web_path} ({mimetype})")
                elif processing_status == 'completed': 
                     if not rpath: app.logger.warning(f"SLIDESHOW_VIEW - Media {mid} (batch {batch_id_str}) COMPLETED but missing filepath, EXCLUDED.")
                     elif not (mimetype and mimetype.startswith(('image/', 'video/', 'audio/'))):
                         app.logger.info(f"SLIDESHOW_VIEW - Media {mid} (mimetype: {mimetype}) in batch {batch_id_str} COMPLETED but not playable type, EXCLUDED.")
            elif mdata: 
                app.logger.info(f"SLIDESHOW_VIEW - Media {mid} (batch {batch_id_str}) EXCLUDED. Hidden: {is_hidden}, Status: {processing_status}")
        
        app.logger.info(f"SLIDESHOW_VIEW - Final js_media_list for slideshow (batch {batch_id_str}): count={len(js_media_list)}")
        app.logger.debug(f"SLIDESHOW_VIEW - Final js_media_list content: {json.dumps(js_media_list, indent=2)}")

        return render_template('slideshow.html', batch=batch_info, media_data_json=json.dumps(js_media_list), is_public_view=False) 
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error in slideshow for {str(batch_id)}: {e}"); flash("Error loading slideshow data.",'danger'); return redirect(url_for('collection_view', batch_id=str(batch_id)))
    except Exception as e: app.logger.error(f"Unexpected error in slideshow for {str(batch_id)}: {e}", exc_info=True); flash("Error loading slideshow.", "danger"); return redirect(url_for('collection_view', batch_id=str(batch_id)))

@app.route('/batch/<string:batch_id>/toggle_share', methods=['POST']) 
@login_required
@owner_or_admin_access_required(item_type='batch') 
def toggle_share_batch(batch_id, batch_data): 
    # ... (Unchanged from your last version - this should be working now) ...
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        current_token = batch_data.get('share_token')
        is_currently_shared_str = batch_data.get('is_shared', '0')
        new_shared_status_bool = not (is_currently_shared_str == '1')
        update_data = {'is_shared': '1' if new_shared_status_bool else '0'}
        new_token_generated = False
        if new_shared_status_bool: 
            if not current_token: 
                current_token = secrets.token_urlsafe(24); update_data['share_token'] = current_token
                redis_client.set(f'share_token:{current_token}', batch_id) ; new_token_generated = True
                app.logger.info(f"Generated new share token for batch {batch_id}.")
        redis_client.hmset(f'batch:{batch_id}', update_data)
        app.logger.info(f"Batch {batch_id} sharing toggled to: {'Public' if new_shared_status_bool else 'Private'}")
        if new_shared_status_bool:
            share_url = url_for('public_batch_view', share_token=current_token, _external=True)
            flash_message = f'Batch "{batch_data.get("name")}" is now <strong>Publicly Shared</strong>. '
            flash_message += f'Share link: <a href="{share_url}" target="_blank" class="alert-link">{share_url}</a>'
            flash(flash_message, 'success')
        else:
            flash(f'Batch "{batch_data.get("name")}" is now <strong>Private</strong>. Public links are deactivated.', 'info')
        return redirect(url_for('collection_view', batch_id=batch_id))
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error toggling share for batch {batch_id}: {e}"); flash("Database error updating sharing status.", "danger"); return redirect(url_for('collection_view', batch_id=batch_id))
    except Exception as e: app.logger.error(f"Unexpected error in toggle_share_batch for {batch_id}: {e}", exc_info=True); flash("An unexpected error occurred.", "danger"); return redirect(url_for('collection_view', batch_id=batch_id))


@app.route('/public/batch/<share_token>')
def public_batch_view(share_token):
    # ... (Unchanged from your file, includes processing_status check) ...
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        batch_id = redis_client.get(f'share_token:{share_token}')
        if not batch_id:
            app.logger.warning(f"Invalid or expired share token used for public batch view: {share_token}")
            return render_template('public_link_invalid.html', reason="The share link is invalid or has expired."), 404
        batch_info = redis_client.hgetall(f'batch:{batch_id}')
        if not batch_info or batch_info.get('is_shared', '0') != '1':
            app.logger.warning(f"Attempt to access non-shared/non-existent batch {batch_id} via token {share_token}.")
            return render_template('public_link_invalid.html', reason="This batch is not currently shared or does not exist."), 403
        batch_info['id'] = batch_id
        batch_info['share_token'] = share_token 
        media_ids = redis_client.lrange(f'batch:{batch_id}:media_ids', 0, -1)
        media_list = []
        valid_items_count = 0
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata and mdata.get('is_hidden', '0') == '0' and mdata.get('processing_status', 'completed') == 'completed': 
                rpath = mdata.get('filepath')
                if rpath:
                    mdata['web_path'] = url_for('static', filename=f"uploads/{rpath.lstrip('/')}")
                    mdata['processing_status'] = 'completed' 
                    media_list.append(mdata)
                    valid_items_count +=1
                elif mdata.get('processing_status') == 'completed':
                    app.logger.warning(f"Public View: Completed media {mid} in batch {batch_id} missing filepath.")
        batch_info['item_count'] = valid_items_count
        return render_template('public_view.html', batch=batch_info, media_items=media_list)
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error in public_batch_view for token {share_token}: {e}")
        return render_template('public_link_invalid.html', reason="A database error occurred while trying to access the shared content."), 500

@app.route('/public/slideshow/<share_token>')
def public_slideshow_view(share_token):
    # ... (Unchanged from your file, includes processing_status check) ...
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        batch_id = redis_client.get(f'share_token:{share_token}') 
        if not batch_id:
            return render_template('public_link_invalid.html', reason="Invalid or expired link for slideshow."), 404
        batch_info = redis_client.hgetall(f'batch:{batch_id}')
        if not batch_info or batch_info.get('is_shared', '0') != '1':
            return render_template('public_link_invalid.html', reason="This slideshow is not currently shared or available."), 403
        batch_info['id'] = batch_id
        batch_info['share_token'] = share_token
        media_ids = redis_client.lrange(f'batch:{batch_id}:media_ids', 0, -1)
        js_media_list = []
        for mid in media_ids:
            mdata = redis_client.hgetall(f'media:{mid}')
            if mdata and mdata.get('is_hidden', '0') == '0' and mdata.get('processing_status', 'completed') == 'completed':
                rpath = mdata.get('filepath')
                if rpath and mdata.get('mimetype','').startswith(('image/', 'video/', 'audio/')):
                    web_path = url_for('static', filename=f"uploads/{rpath.lstrip('/')}")
                    js_media_list.append({ 'filepath': web_path, 'mimetype': mdata.get('mimetype'), 'original_filename': mdata.get('original_filename', 'unknown') })
        return render_template('slideshow.html', batch=batch_info, media_data_json=json.dumps(js_media_list), is_public_view=True)
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error in public_slideshow_view for token {share_token}: {e}")
        return render_template('public_link_invalid.html', reason="Error accessing shared slideshow."), 500

@app.route('/media/<media_id>/toggle_hidden', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media') 
def toggle_hidden(media_id, media_data):
    # ... (Unchanged from your file) ...
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        current_hidden_status = media_data.get('is_hidden', '0')
        new_status = '0' if current_hidden_status == '1' else '1'
        redis_client.hset(f'media:{media_id}', 'is_hidden', new_status)
        action_word = 'visible' if new_status == '0' else 'hidden'
        flash(f"Media item '{media_data.get('original_filename', media_id)}' is now {action_word}.", 'success')
        return redirect(url_for('collection_view', batch_id=media_data['batch_id']))
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error toggling hidden status for media {media_id}: {e}")
        flash("Database error updating media visibility.", "danger")
        return redirect(request.referrer or url_for('index'))

@app.route('/media/<media_id>/toggle_liked', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media') 
def toggle_liked(media_id, media_data):
    # ... (Unchanged from your file) ...
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        current_liked_status = media_data.get('is_liked', '0')
        new_status = '0' if current_liked_status == '1' else '1'
        redis_client.hset(f'media:{media_id}', 'is_liked', new_status)
        action_word = 'unliked' if new_status == '0' else 'liked'
        flash(f"Media item '{media_data.get('original_filename', media_id)}' {action_word}.", 'success')
        return redirect(url_for('collection_view', batch_id=media_data['batch_id']))
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error toggling liked status for media {media_id}: {e}")
        flash("Database error updating media like status.", "danger")
        return redirect(request.referrer or url_for('index'))

@app.route('/media/<media_id>/delete', methods=['POST'])
@login_required
@owner_or_admin_access_required(item_type='media') 
def delete_media(media_id, media_data):
    # ... (Unchanged from your file) ...
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        batch_id_for_redirect = media_data.get('batch_id')
        filepath_from_redis = media_data.get('filepath') 
        if filepath_from_redis:
            disk_filepath_to_delete = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filepath_from_redis)
            try:
                if os.path.exists(disk_filepath_to_delete): os.remove(disk_filepath_to_delete); app.logger.info(f"Deleted file from disk: {disk_filepath_to_delete}")
                else: app.logger.warning(f"File not found on disk for deletion: {disk_filepath_to_delete} (media_id: {media_id})")
            except OSError as e: app.logger.error(f"OS error deleting file {disk_filepath_to_delete}: {e}")
        else: app.logger.warning(f"No filepath found in Redis for media_id {media_id}. Cannot delete from disk.")
        pipe = redis_client.pipeline()
        if batch_id_for_redirect: pipe.lrem(f'batch:{batch_id_for_redirect}:media_ids', 0, media_id)
        pipe.delete(f'media:{media_id}'); pipe.execute()
        flash(f"Media item '{media_data.get('original_filename', media_id)}' deleted successfully.", 'success')
        if batch_id_for_redirect: return redirect(url_for('collection_view', batch_id=batch_id_for_redirect))
        return redirect(url_for('index')) 
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error deleting media {media_id}: {e}"); flash("Database error deleting media item.", "danger"); return redirect(request.referrer or url_for('index'))

@app.route('/batch/<uuid:batch_id>/delete', methods=['POST']) 
@login_required
@owner_or_admin_access_required(item_type='batch') 
def delete_batch(batch_id, batch_data): 
    # ... (Unchanged from your file, ensure str(batch_id) is used for Redis/disk) ...
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        batch_id_str = str(batch_id) 
        user_id_of_batch_owner = batch_data.get('user_id') 
        if user_id_of_batch_owner: 
            batch_directory_on_disk = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], user_id_of_batch_owner, batch_id_str)
            if os.path.exists(batch_directory_on_disk) and os.path.isdir(batch_directory_on_disk):
                try: shutil.rmtree(batch_directory_on_disk); app.logger.info(f"Deleted batch directory from disk: {batch_directory_on_disk}")
                except OSError as e: app.logger.error(f"OS error deleting batch directory {batch_directory_on_disk}: {e}"); flash("Error deleting batch files from disk. Some files may remain.", "warning") 
            else: app.logger.warning(f"Batch directory not found on disk for deletion: {batch_directory_on_disk}")
        else: app.logger.error(f"Cannot determine batch directory for deletion: user_id missing for batch {batch_id_str}.")
        media_ids_in_batch = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1)
        pipe = redis_client.pipeline()
        if media_ids_in_batch:
            for m_id in media_ids_in_batch:
                media_item_data = redis_client.hgetall(f'media:{m_id}')
                if media_item_data.get('processing_status') in ['queued', 'processing'] and media_item_data.get('mimetype') == 'video/x-matroska':
                    temp_input_path_on_disk = media_item_data.get('filepath','') 
                    if temp_input_path_on_disk:
                        full_temp_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], temp_input_path_on_disk)
                        if os.path.exists(full_temp_path):
                            try: os.remove(full_temp_path); app.logger.info(f"Cleaned leftover temp MKV: {full_temp_path}")
                            except OSError as e_rm_temp: app.logger.error(f"Error cleaning temp MKV {full_temp_path}: {e_rm_temp}")
                pipe.delete(f'media:{m_id}') 
        pipe.delete(f'batch:{batch_id_str}:media_ids') 
        pipe.delete(f'batch:{batch_id_str}')           
        if batch_data.get('share_token'): pipe.delete(f"share_token:{batch_data['share_token']}")
        if user_id_of_batch_owner: pipe.lrem(f'user:{user_id_of_batch_owner}:batches', 0, batch_id_str)
        pipe.execute()
        flash(f'Batch "{batch_data.get("name", batch_id_str)}" and all its media deleted successfully.', 'success')
        return redirect(url_for('index'))
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error deleting batch {str(batch_id)}: {e}"); flash("A database error occurred while deleting the batch.", "danger"); return redirect(url_for('index'))
    except Exception as e: app.logger.error(f"Unexpected error deleting batch {str(batch_id)}: {e}", exc_info=True); flash("An unexpected error occurred.", "danger"); return redirect(url_for('index'))

@app.route('/batch/<uuid:batch_id>/rename', methods=['POST']) 
@login_required
def rename_batch(batch_id): 
    # ... (Unchanged from your file) ...
    if not redis_client: return jsonify({'success': False, 'message': 'Database service unavailable.'}), 503
    batch_id_str = str(batch_id) 
    batch_data = redis_client.hgetall(f'batch:{batch_id_str}')
    if not batch_data: current_app.logger.warn(f"Rename attempt for non-existent batch UUID (str): {batch_id_str}"); return jsonify({'success': False, 'message': 'Batch not found.'}), 404
    owner_username = batch_data.get('user_id')
    if not owner_username: current_app.logger.error(f"Batch {batch_id_str} is missing 'user_id' field in Redis."); return jsonify({'success': False, 'message': 'Batch data inconsistent.'}), 500
    if owner_username != session.get('username') and not session.get('is_admin'): current_app.logger.warn(f"Unauthorized rename for batch {batch_id_str} by user {session.get('username')}"); return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    new_name = request.form.get('new_name')
    if not new_name or len(new_name.strip()) == 0: return jsonify({'success': False, 'message': 'New name cannot be empty.'}), 400
    MAX_BATCH_NAME_LENGTH = 255 
    if len(new_name.strip()) > MAX_BATCH_NAME_LENGTH: return jsonify({'success': False, 'message': f'Name cannot exceed {MAX_BATCH_NAME_LENGTH} chars.'}), 400
    old_name = batch_data.get('name', 'Unnamed Batch') 
    new_name_stripped = new_name.strip()
    if old_name == new_name_stripped: return jsonify({'success': True, 'message': 'Batch name is already set to this value.', 'new_name': new_name_stripped }), 200
    try:
        redis_client.hset(f'batch:{batch_id_str}', 'name', new_name_stripped)
        redis_client.hset(f'batch:{batch_id_str}', 'last_modified_timestamp', datetime.datetime.now().timestamp())
        current_app.logger.info(f"Batch '{old_name}' (ID: {batch_id_str}) renamed to '{new_name_stripped}' by user {session.get('username')}")
        return jsonify({'success': True, 'message': f'Batch "{old_name}" renamed to "{new_name_stripped}".', 'new_name': new_name_stripped }), 200
    except redis.exceptions.RedisError as e: current_app.logger.error(f"Redis error renaming batch {batch_id_str}: {e}", exc_info=True); return jsonify({'success': False, 'message': 'DB error saving new name.'}), 500
    except Exception as e: current_app.logger.error(f"Unexpected error renaming batch {batch_id_str}: {e}", exc_info=True); return jsonify({'success': False, 'message': 'Unexpected server error.'}), 500

@app.route('/batch/<uuid:batch_id>/export') 
@login_required
@owner_or_admin_access_required(item_type='batch')
def export_batch(batch_id, batch_data): 
    # ... (Unchanged from your file, ensure str(batch_id) is used for Redis/disk) ...
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        batch_id_str = str(batch_id) 
        memory_zip_file = BytesIO()
        files_added_count = 0
        with zipfile.ZipFile(memory_zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            media_ids = redis_client.lrange(f'batch:{batch_id_str}:media_ids', 0, -1)
            for mid in media_ids:
                minfo = redis_client.hgetall(f'media:{mid}')
                if minfo and minfo.get('is_hidden', '0') == '0' and minfo.get('processing_status', 'completed') == 'completed': 
                    rpath = minfo.get('filepath') 
                    if rpath:
                        disk_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], rpath)
                        if os.path.exists(disk_path) and os.path.isfile(disk_path):
                            arc_name = minfo.get('original_filename', os.path.basename(rpath))
                            zf.write(disk_path, arcname=arc_name); files_added_count += 1
                        elif minfo.get('processing_status') == 'completed': app.logger.warning(f"Export: Completed file missing: '{disk_path}' (media '{mid}', batch '{batch_id_str}').")
                    elif minfo.get('processing_status') == 'completed': app.logger.warning(f"Export: Completed filepath missing in Redis (media '{mid}', batch '{batch_id_str}').")
            if files_added_count == 0: flash("No completed non-hidden files found to export.", "warning"); return redirect(url_for('collection_view', batch_id=batch_id_str))
        memory_zip_file.seek(0)
        timestamp_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_batch_name = secure_filename(batch_data.get('name', 'batch')).replace(' ', '_')
        zip_filename = f"LightBox_{safe_batch_name}_Export_{timestamp_str}.zip"
        return send_file(memory_zip_file, mimetype='application/zip', as_attachment=True, download_name=zip_filename)
    except redis.exceptions.RedisError as e: app.logger.error(f"Redis error during export for batch {str(batch_id)}: {e}"); flash("DB error during export.", "danger"); return redirect(url_for('collection_view', batch_id=str(batch_id)))
    except Exception as e: app.logger.error(f"Unexpected error during export for batch {str(batch_id)}: {e}", exc_info=True); flash("Unexpected error during export.", "danger"); return redirect(url_for('collection_view', batch_id=str(batch_id)))

# --- Admin Routes ---
# ... (Your admin routes - unchanged) ...
@app.route('/admin/users')
@login_required
@admin_required
def admin_dashboard():
    if not redis_client: abort(503, description="Database service unavailable.")
    try:
        all_usernames = redis_client.smembers('users')
        sorted_usernames = sorted(list(all_usernames), key=lambda s: s.lower())
        users_list = []
        for uname in sorted_usernames:
            user_info = redis_client.hgetall(f'user:{uname}')
            user_info['username'] = uname 
            user_info['batch_count'] = redis_client.llen(f'user:{uname}:batches')
            users_list.append(user_info)
        return render_template('admin_dashboard.html', users=users_list)
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error in admin_dashboard: {e}")
        flash("Error loading user data for admin dashboard.", "danger")
        return redirect(url_for('index'))

@app.route('/admin/change_password', methods=['POST'])
@login_required
@admin_required
def change_user_password():
    if not redis_client: abort(503, description="Database service unavailable.")
    target_username = request.form.get('username')
    new_password = request.form.get('new_password')
    if not target_username or not new_password:
        flash('Username and new password are required.', 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        if not redis_client.sismember('users', target_username):
            flash(f'User "{target_username}" not found.', 'danger')
            return redirect(url_for('admin_dashboard'))
        if len(new_password) < 6: 
            flash('New password must be at least 6 characters long.', 'danger')
            return redirect(url_for('admin_dashboard'))
        redis_client.hset(f'user:{target_username}', 'password_hash', generate_password_hash(new_password))
        flash(f'Password successfully updated for user "{target_username}".', 'success')
    except redis.exceptions.RedisError as e:
        app.logger.error(f"Redis error changing password for {target_username}: {e}")
        flash("A database error occurred while changing the password.", "danger")
    return redirect(url_for('admin_dashboard'))

# --- Error handlers ---
# ... (Your existing error handlers - unchanged) ...
@app.errorhandler(404)
def page_not_found_error(e):
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        app.logger.warning(f"JSON 404 for {request.url}: {e}")
        return jsonify(error=str(e.description if hasattr(e, 'description') else "Not Found")), 404
    return render_template('404.html', error=e), 404

@app.errorhandler(413)
def request_entity_too_large_error(e):
    max_size_bytes = app.config.get('MAX_CONTENT_LENGTH', 0)
    max_size_mb = max_size_bytes // (1024 * 1024) if max_size_bytes > 0 else "configured limit"
    flash(f"Upload failed: File or total upload size is too large. Maximum allowed is {max_size_mb}MB.", "danger")
    return redirect(request.referrer or url_for('index')), 413

@app.errorhandler(500)
def internal_server_error(e):
    original_exception = getattr(e, 'original_exception', None)
    if original_exception:
        app.logger.error(f"Internal Server Error: {e.name if hasattr(e, 'name') else 'Error'} - Description: {e.description if hasattr(e, 'description') else 'N/A'}", exc_info=original_exception)
    else:
        app.logger.error(f"Internal Server Error: {e}", exc_info=True) 
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(error="Internal server error", message=str(e.description if hasattr(e, 'description') else "An unexpected error occurred.")), 500
    return render_template('500.html', error=e), 500

@app.errorhandler(503) 
def service_unavailable_error(e):
    error_desc = getattr(e, 'description', "A required service is temporarily unavailable. Please try again later.")
    app.logger.error(f"Service Unavailable (503): {error_desc}")
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(error="Service unavailable", message=error_desc), 503
    return render_template('503.html', error_message=error_desc), 503

# --- Main Execution ---
if __name__ == '__main__':
    print("--- Starting Flask App in Development Mode (for local testing only) ---")
    upload_folder_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    if not os.path.exists(upload_folder_path):
        os.makedirs(upload_folder_path)
        print(f"Created UPLOAD_FOLDER at: {upload_folder_path}")
    
    app.run(debug=True, host='0.0.0.0', port=5102)
