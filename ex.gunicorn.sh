#!/bin/bash

# Navigate to the project directory
# This is good if you run the script from elsewhere, but if you always run it
# from /home/www/newvid, it's not strictly necessary but doesn't hurt.
cd /home/www/newvid

# Activate the virtual environment
source /home/www/newvid/venv/bin/activate

# --- IMPORTANT: SET YOUR SECRET ENVIRONMENT VARIABLES HERE ---
# 1. Flask Secret Key (Generate a new random one for production)
#    Example generation: python -c 'import secrets; print(secrets.token_hex(32))'
export FLASK_SECRET_KEY="long random string"

# 2. Redis Password (The password your Redis server is configured to use)
#    If your Redis has no password, you can leave this unset or set it to an empty string,
#    but ensure your app.py's Redis connection logic handles an empty password correctly (which it does).
#    It's highly recommended to have a password on Redis in production.
export REDIS_PASSWORD="your redis password"

# 3. Initial Admin User Password for LightBox
#    Set this to the strong password you want for the 'admin' user account.
export LIGHTBOX_ADMIN_PASSWORD="Hard code your admin login password here"

# 4. Optional: Path to FFmpeg (if not in the system PATH for the Gunicorn user)
#    If 'ffmpeg' command works directly in the shell for the user running Gunicorn, this isn't needed.
export FFMPEG_PATH="/usr/bin/ffmpeg" # Or your actual path

# --- End of Environment Variables ---

echo "Starting Gunicorn for LightBox..."
echo "Flask Secret Key is SET (value not shown for security)" # Just confirm it's being processed
echo "Redis Password is SET (value not shown for security)"
echo "Lightbox Admin Password is SET (value not shown for security)"


# Run Gunicorn with logging enabled
# Ensure app:app correctly points to your Flask app instance named 'app' in your 'app.py' file.
exec gunicorn --workers 7 \
    --bind 0.0.0.0:5102 \
    --timeout 3600 \
    --access-logfile /home/www/newvid/gunicorn_access.log \
    --error-logfile /home/www/newvid/gunicorn_error.log \
    app:app
