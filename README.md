# LightBox: A Flask & Celery Powered Media Slideshow Creator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

LightBox is a web application built with Flask, Celery, and Redis that allows users to upload images, videos (including automatic MKV to MP4 conversion), and audio files, organize them into collections ("Lightboxes"), and view them in a smooth, interactive slideshow player. It also features user authentication, batch management, and public sharing capabilities.

This project is primarily for educational purposes, demonstrating a full-stack web application with background task processing and modern user interface features.

## Key Features

*   **Versatile Media Upload:** Supports images (JPG, PNG, GIF, WebP, etc.), videos (MP4, MOV, WebM, etc.), audio (MP3, WAV, etc.), and PDFs.
*   **Automatic MKV to MP4 Conversion:** Seamless background conversion of MKV files to a web-friendly MP4 format (H.264/AAC) using FFmpeg and Celery.
*   **"Lightbox" (Batch) Management:**
    *   Create new Lightboxes or add media to existing ones.
    *   Rename and delete Lightboxes.
    *   Export Lightboxes as ZIP archives (completed, non-hidden media).
*   **Interactive Slideshow Player:**
    *   Smooth fade transitions between media items.
    *   Comprehensive playback controls (play/pause, next/previous, volume, progress bar for A/V).
    *   Immersive fullscreen mode.
    *   Keyboard (space, arrows, 'F') and touch swipe navigation.
    *   Auto-hiding controls and navbar for an uncluttered viewing experience.
    *   Loading indicators for media.
    *   Dynamic volume icon.
*   **Gallery View:**
    *   Manage individual media items within a Lightbox (hide/unhide, like/unlike, delete).
    *   Filter media items by status (completed, processing, failed, visible, hidden, liked).
    *   Visual indicators for processing and failed items.
*   **User Authentication:** Secure registration and login system.
*   **Public Sharing:** Share Lightboxes with others via unique, revocable links.
*   **Admin Panel:** Basic user management (view users, change passwords).
*   **Responsive Design:** Built with Bootstrap 5 for usability across desktops, tablets, and mobile devices.

## Tech Stack

*   **Backend:** Python 3, Flask
*   **Task Queue:** Celery
*   **Message Broker & In-Memory Database:** Redis
*   **Video/Audio Processing:** FFmpeg
*   **Frontend:** HTML5, CSS3 (with Bootstrap 5), JavaScript, Jinja2
*   **Deployment (Example):** Gunicorn, Docker, Docker Compose (Docker setup to be detailed further)

## Setup and Installation (Ubuntu/Linux)

### Prerequisites

*   Python 3.8+ and pip
*   Redis Server (e.g., `sudo apt update && sudo apt install redis-server`)
*   FFmpeg (e.g., `sudo apt update && sudo apt install ffmpeg`)
*   Git (e.g., `sudo apt update && sudo apt install git`)

### Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/hapnesbitt/lightbox.git
    cd lightbox 
    ```

2.  **Create and activate a Python virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    It is highly recommended to use an environment variable management method suitable for your deployment. For local development, you can create a `.env` file in the project root (ensure `.env` is in your `.gitignore`).
    Alternatively, an example startup script `ex.gunicorn.sh` is provided. **Copy `ex.gunicorn.sh` to `gunicorn.sh`, edit `gunicorn.sh` with your actual secrets, and then make it executable (`chmod +x gunicorn.sh`). Your actual `gunicorn.sh` (with secrets) should be ignored by Git.**

    Required environment variables:
    *   `FLASK_SECRET_KEY`: A long, random string for session security. Generate one with: `python -c 'import secrets; print(secrets.token_hex(32))'`
    *   `REDIS_HOST`: Defaults to `localhost` if not set.
    *   `REDIS_PORT`: Defaults to `6379` if not set.
    *   `REDIS_PASSWORD`: Set if your Redis instance requires a password (defaults to empty).
    *   `LIGHTBOX_ADMIN_PASSWORD`: Password for the initial 'admin' user. **Change this!**
    *   `FFMPEG_PATH`: Path to the FFmpeg executable. Defaults to `ffmpeg` (assumes it's in the system PATH).

5.  **Run the Application:**
    *   **Ensure your Redis server is running:**
        ```bash
        sudo systemctl status redis-server 
        # If not active: sudo systemctl start redis-server
        ```
    *   **Start the Celery worker** (in a separate terminal, from the project root, with the virtual environment activated):
        ```bash
        celery -A app.celery worker -l info 
        ```
        *(This assumes your Celery app instance in `app.py` is named `celery` and accessible as `app.celery` via `app = Flask(...)` then `celery = make_celery(app)`)*
    *   **Run the Flask application using Gunicorn (example):**
        Ensure `gunicorn.sh` is executable (`chmod +x gunicorn.sh`) and configured with your environment variables.
        ```bash
        ./gunicorn.sh 
        ```
        Or run the Flask development server (for local testing only):
        ```bash
        flask run --host=0.0.0.0 --port=5102
        ```
    Access the application in your browser, typically at `http://127.0.0.1:5102` (or your server's IP if accessing remotely). The 'admin' user (username: `admin`) is automatically created with the password set by `LIGHTBOX_ADMIN_PASSWORD`.

## Docker Deployment

(This section will be expanded with `Dockerfile` and `docker-compose.yml` instructions for easier deployment using containers.)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to report bugs, suggest features, or submit code changes.

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

## Author & Contact

*   **Ross Nesbitt** ([hapnesbitt on GitHub](https://github.com/hapnesbitt))
*   More Projects & Info: [https://rossnesbitt.gotdns.com](https://rossnesbitt.gotdns.com)
*   For project-specific issues or feature requests, please use the [GitHub Issues tracker](https://github.com/hapnesbitt/lightbox/issues).

---
