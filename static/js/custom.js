// static/js/custom.js

function formatTime(timeInSeconds) {
    if (isNaN(timeInSeconds) || timeInSeconds === Infinity || timeInSeconds < 0) {
        return '--:--';
    }
    const totalSeconds = Math.floor(timeInSeconds);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
}

document.addEventListener('DOMContentLoaded', function() {
    const slideshowContainer = document.getElementById('slideshow-container');
    if (slideshowContainer && typeof mediaItems !== 'undefined' && Array.isArray(mediaItems)) {
        console.log("DOM Ready: Initializing slideshow.");
        initSlideshow();
    } else if (slideshowContainer) {
        console.warn("DOM Ready: Slideshow container found, but mediaItems is undefined or not an array.");
    }

    const fileUploadInput = document.querySelector('input[type="file"][name="files[]"]');
    if (fileUploadInput) {
        fileUploadInput.addEventListener('change', function() {
            const feedback = this.closest('.card-body')?.querySelector('.form-text.upload-feedback, .form-text'); // Adjusted selector for index/upload pages
            if (this.files && this.files.length > 0 && feedback) {
                feedback.textContent = `${this.files.length} file(s) selected.`;
            } else if (feedback) {
                // Restore default text (assuming it's simple, or store/retrieve from data-attribute if complex)
                const defaultUploadText = "Allowed: Images, Videos, Audio, PDF. MKVs are converted."; // Example, make dynamic if needed
                const defaultCollectionText = "Allowed file types: Images, Videos, Audio, PDF";
                if (feedback.classList.contains('upload-feedback')) { // For index.html
                     feedback.textContent = defaultUploadText;
                } else { // For collection.html (original logic)
                     feedback.textContent = defaultCollectionText;
                }
            }
        });
    }
});

function initSlideshow() {
    console.log("initSlideshow: Starting initialization.");

    // --- DOM Element References ---
    const slideshowContainer = document.getElementById('slideshow-container');
    const imageEl = document.getElementById('slideshow-image');
    const videoEl = document.getElementById('slideshow-video');
    const audioEl = document.getElementById('slideshow-audio');

    let loadingSpinner = slideshowContainer.querySelector('.loading-spinner');
    if (!loadingSpinner) {
        loadingSpinner = document.createElement('div');
        loadingSpinner.className = 'loading-spinner';
        loadingSpinner.innerHTML = '<div class="spinner-border text-light" style="width: 3rem; height: 3rem;" role="status"><span class="visually-hidden">Loading...</span></div>';
        loadingSpinner.style.cssText = 'display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10;';
        slideshowContainer.appendChild(loadingSpinner);
    }

    const playPauseBtn = document.getElementById('play-pause-btn');
    const playPauseIcon = document.getElementById('play-pause-icon');
    const nextBtn = document.getElementById('next-btn');
    const prevBtn = document.getElementById('prev-btn');
    const downloadLink = document.getElementById('download-link');
    const fullscreenBtn = document.getElementById('fullscreen-btn');
    const volumeControl = document.getElementById('volume-control');
    const volumeIcon = volumeControl?.parentElement?.querySelector('i');
    const counterEl = document.getElementById('counter');
    const mediaProgressBar = document.getElementById('media-progress-bar');
    const progressBarGroup = document.getElementById('progress-bar-group');
    const timeDisplay = document.getElementById('time-display');
    const controlsContainerEl = document.querySelector('.controls-container');
    const navbarEl = document.querySelector('.slideshow-page-body .navbar');
    const returnLinkEl = document.getElementById('return-link');

    const brokenImagePath = '/static/images/broken_image.png';
    const videoPlaceholderPath = '/static/images/video_placeholder.png';
    const audioPlaceholderPath = '/static/images/audio_placeholder.png';
    const filePlaceholderPath = '/static/images/file_placeholder.png';

    // --- State Variables ---
    let currentIndex = 0;
    let imageTimer = null;
    const DEFAULT_IMAGE_DURATION = 15000;
    // RENAMED: isPlayingStateForImages -> isSlideshowPlayingIntent for clarity
    let isSlideshowPlayingIntent = true; // User's general intent for the slideshow to be playing
    let currentMediaElementForSeek = null;
    let isDraggingProgressBar = false;
    let hasUserInteractedForSound = false;
    let controlsHideTimer = null;
    let isAppInitiatedFullscreen = false;
    const CONTROLS_HIDE_DELAY = 3000;
    const MEDIA_TRANSITION_DURATION = 300;
    let transitioningAway = false;

    // ADDED FOR ATTEMPT #3: For handling unexpected media pauses
    let unexpectedPauseTimer = null;
    const UNEXPECTED_PAUSE_GRACE_PERIOD = 150; // milliseconds

    if (!mediaItems || mediaItems.length === 0) {
        console.warn('initSlideshow: No media items. Aborting.');
        if (slideshowContainer) slideshowContainer.innerHTML = '<p style="color: white; text-align: center; width:100%;">No media items to display.</p>';
        if (controlsContainerEl) controlsContainerEl.style.display = 'none';
        return;
    }
    console.log(`initSlideshow: Found ${mediaItems.length} media items.`);

    const showLoadingSpinner = () => { if (loadingSpinner) loadingSpinner.style.display = 'block'; };
    const hideLoadingSpinner = () => { if (loadingSpinner) loadingSpinner.style.display = 'none'; };

    // ADDED FOR ATTEMPT #3: Helper to clear the unexpected pause assessment
    function clearUnexpectedPauseAssessment() {
        if (unexpectedPauseTimer) {
            clearTimeout(unexpectedPauseTimer);
            unexpectedPauseTimer = null; // Crucial: Clear the timer ID reference
            console.debug("clearUnexpectedPauseAssessment: Cleared pending unexpectedPauseTimer.");
        }
    }

    function updateVolumeIcon() {
        if (!volumeControl || !volumeIcon) return;
        const currentVolume = parseFloat(volumeControl.value);
        let isMuted = false;
        if (currentMediaElementForSeek) isMuted = currentMediaElementForSeek.muted;
        else if (videoEl && audioEl) isMuted = videoEl.muted || audioEl.muted;

        if (isMuted || currentVolume === 0) volumeIcon.className = 'bi bi-volume-mute-fill';
        else if (currentVolume <= 0.5) volumeIcon.className = 'bi bi-volume-down-fill';
        else volumeIcon.className = 'bi bi-volume-up-fill';
    }

    function updateMediaTimelineUI() {
        if (!currentMediaElementForSeek || !mediaProgressBar || !timeDisplay) return;
        const media = currentMediaElementForSeek;
        if (!isNaN(media.duration) && media.duration > 0 && !isDraggingProgressBar) {
            mediaProgressBar.max = media.duration;
            mediaProgressBar.value = isNaN(media.currentTime) ? 0 : media.currentTime;
        } else if (!isDraggingProgressBar) {
            mediaProgressBar.max = 100;
            mediaProgressBar.value = 0;
        }
        timeDisplay.textContent = `${formatTime(media.currentTime)} / ${formatTime(media.duration)}`;
    }

    function setupMediaElementSpecificListeners(mediaElement) {
        if (!mediaElement) return;
        clearMediaElementSpecificListeners(mediaElement);

        mediaElement.onloadedmetadata = () => {
            console.debug("onloadedmetadata:", mediaElement.id, "Duration:", mediaElement.duration);
            hideLoadingSpinner();
            updateMediaTimelineUI();
            updatePlayPauseVisuals();
            updateVolumeIcon();
            // Check isSlideshowPlayingIntent for A/V media
            if ((isSlideshowPlayingIntent || !mediaElement.paused) && !mediaElement.classList.contains('media-active')) {
                mediaElement.classList.add('media-active');
            }
        };
        mediaElement.ontimeupdate = () => { if (!isDraggingProgressBar) updateMediaTimelineUI(); };

        // MODIFIED FOR ATTEMPT #3: `onplay` handler
        mediaElement.onplay = () => {
            clearUnexpectedPauseAssessment(); // Clear any pending pause assessment
            console.debug(`onplay: ${mediaElement.id}. Setting isSlideshowPlayingIntent = true.`);
            isSlideshowPlayingIntent = true; // Reflect that media is actively playing
            updatePlayPauseVisuals();
            updateMediaTimelineUI();
            resetControlsHideTimer();
        };

        // MODIFIED FOR ATTEMPT #3: `onpause` handler
        mediaElement.onpause = () => {
            console.debug(`onpause: ${mediaElement.id}. TransitioningAway: ${transitioningAway}. Current isSlideshowPlayingIntent: ${isSlideshowPlayingIntent}`);
            // DO NOT clearUnexpectedPauseAssessment() here, as this might be the event that STARTS it.

            if (!transitioningAway) { // Pause not due to transitioning to another slide
                if (isSlideshowPlayingIntent) { // If we thought we should be playing
                    console.debug(`onpause: Unexpected pause for ${mediaElement.id}. Starting grace period timer.`);
                    // Clear any *previous* timer before setting a new one for THIS pause event
                    clearUnexpectedPauseAssessment(); // Ensure only one assessment timer runs
                    unexpectedPauseTimer = setTimeout(() => {
                        // Check if this timer is still relevant (i.e., not cleared by an explicit play or transition)
                        if (unexpectedPauseTimer === null) { // Timer was cleared externally
                            console.debug(`onpause (timeout): Grace period timer for ${mediaElement.id} was cleared. No action.`);
                            return;
                        }
                        unexpectedPauseTimer = null; // Clear reference as we are now executing this timer's callback

                        // Re-check conditions *inside* the timeout callback
                        if (mediaElement.paused && currentMediaElementForSeek === mediaElement && isSlideshowPlayingIntent) {
                            console.debug(`onpause (timeout): Grace period ended for ${mediaElement.id}. Media still paused. Setting isSlideshowPlayingIntent to false.`);
                            isSlideshowPlayingIntent = false;
                            updatePlayPauseVisuals(); // Update visuals as state has changed
                        } else {
                            console.debug(`onpause (timeout): Grace period ended for ${mediaElement.id}, but conditions for state change not met (media playing, different element, or intent already false).`);
                        }
                    }, UNEXPECTED_PAUSE_GRACE_PERIOD);
                } else { // isSlideshowPlayingIntent was already false
                    console.debug("onpause: Media paused. isSlideshowPlayingIntent was already false (likely user-initiated pause).");
                }
            } else { // Pause IS due to transitioningAway
                console.debug("onpause: Media paused as part of transitioning away. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
                // If we are transitioning, any "unexpected pause" concern for the *outgoing* media is moot.
                clearUnexpectedPauseAssessment();
            }

            // Update visuals immediately based on current media element's actual paused state
            updatePlayPauseVisuals();
            updateMediaTimelineUI();
            resetControlsHideTimer();
        };

        mediaElement.onended = () => {
            console.debug("onended:", mediaElement.id);
            onMediaEnded(mediaElement);
        };
        mediaElement.oncanplay = () => {
            console.debug("oncanplay:", mediaElement.id);
            hideLoadingSpinner();
            mediaElement.classList.add('media-active');
        };
        mediaElement.onerror = (e) => {
            console.error("Media Element Error:", mediaElement.id, mediaElement.error, e);
            hideLoadingSpinner();
            const item = mediaItems[currentIndex];
            const originalFilename = item ? (item.original_filename || 'Unknown File') : 'Unknown File';
            imageEl.src = (mediaElement === videoEl) ? videoPlaceholderPath : audioPlaceholderPath;
            imageEl.alt = `Error playing: ${originalFilename}`;
            imageEl.style.display = 'block';
            imageEl.classList.add('media-active');
            if (mediaElement === videoEl) videoEl.style.display = 'none';
            if (mediaElement === audioEl) audioEl.style.display = 'none';
            currentMediaElementForSeek = null;
            if (progressBarGroup) progressBarGroup.style.display = 'none';
            if (isSlideshowPlayingIntent) imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2);
        };
    }

    function clearMediaElementSpecificListeners(mediaElement) {
        if (!mediaElement) return;
        mediaElement.onloadedmetadata = null;
        mediaElement.ontimeupdate = null;
        mediaElement.onplay = null;
        mediaElement.onpause = null;
        mediaElement.onended = null;
        mediaElement.oncanplay = null;
        mediaElement.onerror = null;
        mediaElement.onload = null; // Also clear onload if it was used for images
    }

    // MODIFIED FOR ATTEMPT #3: Call clearUnexpectedPauseAssessment
    async function resetAndHideAllMediaElements() {
        console.debug("resetAndHideAllMediaElements: Hiding media elements. Clearing unexpected pause assessment.");
        clearUnexpectedPauseAssessment(); // Clear it here as we are initiating a change

        [imageEl, videoEl, audioEl].forEach(el => el.classList.remove('media-active'));

        return new Promise(resolve => {
            const oldMediaElement = currentMediaElementForSeek;

            const cleanupAndResolve = () => {
                console.debug("resetAndHideAllMediaElements: cleanupAndResolve running. Old media was:", oldMediaElement ? oldMediaElement.id : "none");
                imageEl.style.display = 'none';
                videoEl.style.display = 'none';
                audioEl.style.display = 'none';

                if (oldMediaElement === videoEl) { videoEl.removeAttribute('src'); videoEl.load(); }
                else if (oldMediaElement === audioEl) { audioEl.removeAttribute('src'); audioEl.load(); }
                imageEl.removeAttribute('src');

                if (oldMediaElement) {
                    clearMediaElementSpecificListeners(oldMediaElement);
                    console.debug("resetAndHideAllMediaElements: Cleared listeners for", oldMediaElement.id);
                }
                currentMediaElementForSeek = null;
                if (progressBarGroup) progressBarGroup.style.display = 'none';
                console.debug("resetAndHideAllMediaElements: Resolving promise.");
                resolve();
            };

            if (oldMediaElement && (oldMediaElement === videoEl || oldMediaElement === audioEl)) {
                console.debug("resetAndHideAllMediaElements: Preparing to pause old A/V media:", oldMediaElement.id);
                transitioningAway = true;
                oldMediaElement.pause();
                console.debug("resetAndHideAllMediaElements: Pause called on", oldMediaElement.id, "transitioningAway is", transitioningAway);
            }
            setTimeout(cleanupAndResolve, MEDIA_TRANSITION_DURATION);
        });
    }

    async function loadMedia(index) {
        if (index < 0 || index >= mediaItems.length) {
            index = (index < 0 && mediaItems.length > 0) ? mediaItems.length - 1 : 0;
            if (mediaItems.length === 0) {
                console.error("loadMedia: mediaItems empty.");
                await resetAndHideAllMediaElements();
                if (slideshowContainer) slideshowContainer.innerHTML = '<p style="color: white; text-align: center; width:100%;">No media items.</p>';
                hideLoadingSpinner();
                return;
            }
        }
        currentIndex = index;
        const item = mediaItems[currentIndex];
        console.log(`loadMedia: Item ${currentIndex + 1}/${mediaItems.length}`, JSON.stringify(item).substring(0, 200) + "...");
        clearTimeout(imageTimer);
        console.debug("loadMedia: Cleared imageTimer (if any).");
        showLoadingSpinner();

        await resetAndHideAllMediaElements(); // This now also calls clearUnexpectedPauseAssessment

        console.debug("loadMedia: Resetting transitioningAway to false after old media handled.");
        transitioningAway = false;

        if (!item || !item.filepath) {
            console.error(`loadMedia: Item ${currentIndex} invalid.`, item);
            imageEl.onload = null;
            imageEl.onerror = null;
            imageEl.src = brokenImagePath;
            imageEl.alt = "Error: Invalid data";
            imageEl.style.display = 'block';
            imageEl.classList.add('media-active');
            hideLoadingSpinner();
            if (counterEl) counterEl.textContent = `${currentIndex + 1}/${mediaItems.length}`;

            if (isSlideshowPlayingIntent) {
                imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2);
                console.debug("loadMedia (broken item): Started imageTimer. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
            } else {
                console.debug("loadMedia (broken item): Not starting imageTimer. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
            }
            updatePlayPauseVisuals();
            return;
        }
        const mediaPath = item.filepath;
        const mimeType = item.mimetype ? item.mimetype.toLowerCase() : 'application/octet-stream';
        const originalFilename = item.original_filename || 'Unknown File';
        if (counterEl) counterEl.textContent = `${currentIndex + 1}/${mediaItems.length}`;
        if (downloadLink && typeof isPublicSlideshowView !== 'undefined' && !isPublicSlideshowView) {
            downloadLink.href = mediaPath;
            downloadLink.setAttribute('download', originalFilename);
            const dlC = downloadLink.closest('.download-container');
            if (dlC) dlC.style.display = '';
        } else if (downloadLink) {
            const dlC = downloadLink.closest('.download-container');
            if (dlC) dlC.style.display = 'none';
        }

        let isAVMedia = false;
        console.debug(`loadMedia: Path: ${mediaPath}, Mime: ${mimeType}`);

        if (mimeType.startsWith('image/')) {
            imageEl.onload = () => { hideLoadingSpinner(); imageEl.classList.add('media-active'); console.debug("Img loaded:", mediaPath); };
            imageEl.onerror = () => {
                console.error("Img onerror:", mediaPath);
                hideLoadingSpinner();
                if (imageEl.src !== brokenImagePath) { imageEl.src = brokenImagePath; imageEl.alt = `Error loading: ${originalFilename}`; }
                imageEl.classList.add('media-active');
            };
            imageEl.src = mediaPath;
            imageEl.alt = originalFilename;
            imageEl.style.display = 'block';

            if (isSlideshowPlayingIntent) {
                imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION);
                console.debug("loadMedia (image): Started imageTimer. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
            } else {
                console.debug("loadMedia (image): Not starting imageTimer. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
            }

        } else if (mimeType.startsWith('video/')) {
            videoEl.src = mediaPath;
            videoEl.style.display = 'block';
            currentMediaElementForSeek = videoEl;
            isAVMedia = true;
            setupMediaElementSpecificListeners(videoEl);
            videoEl.muted = !hasUserInteractedForSound; // Mute initially if no interaction
            if (isSlideshowPlayingIntent) {
                console.debug("loadMedia: Attempting autoplay for video", mediaPath, "as isSlideshowPlayingIntent is true.");
                videoEl.play().catch(e => console.warn(`Vid autoplay ${mediaPath}:`, e.message));
            } else {
                console.debug("loadMedia: Not autoplaying video", mediaPath, "as isSlideshowPlayingIntent is false.");
            }
        } else if (mimeType.startsWith('audio/')) {
            audioEl.src = mediaPath;
            audioEl.style.display = 'block'; // Or 'none' if relying purely on custom controls and no visual for audio element itself
            currentMediaElementForSeek = audioEl;
            isAVMedia = true;
            setupMediaElementSpecificListeners(audioEl);
            audioEl.muted = !hasUserInteractedForSound; // Mute initially if no interaction
            if (isSlideshowPlayingIntent) {
                console.debug("loadMedia: Attempting autoplay for audio", mediaPath, "as isSlideshowPlayingIntent is true.");
                audioEl.play().catch(e => console.warn(`Aud autoplay ${mediaPath}:`, e.message));
            } else {
                console.debug("loadMedia: Not autoplaying audio", mediaPath, "as isSlideshowPlayingIntent is false.");
            }
        } else {
            console.warn("Unsupported type:", mimeType);
            imageEl.onload = null;
            imageEl.onerror = null;
            imageEl.src = filePlaceholderPath;
            imageEl.alt = `Unsupported: ${originalFilename} (${mimeType})`;
            imageEl.style.display = 'block';
            imageEl.classList.add('media-active');
            hideLoadingSpinner();
            if (isSlideshowPlayingIntent) {
                imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2);
                console.debug("loadMedia (unsupported item): Started imageTimer. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
            } else {
                console.debug("loadMedia (unsupported item): Not starting imageTimer. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
            }
        }

        if (isAVMedia && progressBarGroup && currentMediaElementForSeek) {
            progressBarGroup.style.display = 'flex';
            if (currentMediaElementForSeek.readyState >= currentMediaElementForSeek.HAVE_METADATA) updateMediaTimelineUI();
            else {
                if (mediaProgressBar) { mediaProgressBar.max = 100; mediaProgressBar.value = 0; }
                if (timeDisplay) timeDisplay.textContent = '0:00/0:00';
            }
        }
        updatePlayPauseVisuals();
        updateVolumeIcon();
        resetControlsHideTimer();
    }

    function updatePlayPauseVisuals() {
        if (!playPauseIcon || !playPauseBtn) return;
        let isEffectivelyPlaying = false;
        if (currentMediaElementForSeek) {
            isEffectivelyPlaying = !currentMediaElementForSeek.paused && !currentMediaElementForSeek.ended;
        } else if (imageEl.style.display !== 'none' && imageEl.classList.contains('media-active')) {
            // For images, the visual should reflect isSlideshowPlayingIntent
            isEffectivelyPlaying = isSlideshowPlayingIntent;
        }
        playPauseIcon.className = isEffectivelyPlaying ? 'bi bi-pause-fill' : 'bi bi-play-fill';
        playPauseBtn.title = isEffectivelyPlaying ? "Pause (Spacebar)" : "Play (Spacebar)";
    }

    // MODIFIED FOR ATTEMPT #3: Call clearUnexpectedPauseAssessment
    function nextMedia() {
        console.debug("nextMedia: Called. Clearing any unexpected pause assessment.");
        clearUnexpectedPauseAssessment();
        loadMedia((currentIndex + 1) % mediaItems.length);
    }

    // MODIFIED FOR ATTEMPT #3: Call clearUnexpectedPauseAssessment
    function prevMedia() {
        console.debug("prevMedia: Called. Clearing any unexpected pause assessment.");
        clearUnexpectedPauseAssessment();
        loadMedia((currentIndex - 1 + mediaItems.length) % mediaItems.length);
    }

    // MODIFIED FOR ATTEMPT #3: Call clearUnexpectedPauseAssessment and manage isSlideshowPlayingIntent
    function togglePlayPause() {
        console.log("togglePlayPause: Called. Current isSlideshowPlayingIntent (user intent):", isSlideshowPlayingIntent);
        resetControlsHideTimer();
        const item = mediaItems[currentIndex];
        if (!item) return;

        clearUnexpectedPauseAssessment(); // User is explicitly interacting, clear any pending assessment

        if (currentMediaElementForSeek) { // A/V media is active
            if (!currentMediaElementForSeek.paused) { // If it's currently playing, user wants to pause
                console.log("togglePlayPause: A/V - Media is playing. Issuing PAUSE command.");
                currentMediaElementForSeek.pause();
                isSlideshowPlayingIntent = false; // User intends to pause
            } else { // If it's currently paused, user wants to play
                console.log("togglePlayPause: A/V - Media is paused. Issuing PLAY command.");
                if (currentMediaElementForSeek.muted && !hasUserInteractedForSound) {
                    currentMediaElementForSeek.muted = false;
                    hasUserInteractedForSound = true;
                    updateVolumeIcon();
                }
                currentMediaElementForSeek.play().then(() => {
                    console.log("togglePlayPause: A/V - Play command successful.");
                    isSlideshowPlayingIntent = true; // User intends to play, and play succeeded
                    updatePlayPauseVisuals(); // Update visuals after successful play sets state
                }).catch(e => {
                    console.warn("togglePlayPause: A/V - Play command failed:", e.message);
                    // If play failed, ensure intent reflects paused state if it's not already
                    if (isSlideshowPlayingIntent) {
                        isSlideshowPlayingIntent = false;
                    }
                    updatePlayPauseVisuals();
                });
            }
        } else { // Image or other non-A/V media is active
            isSlideshowPlayingIntent = !isSlideshowPlayingIntent;
            console.log("togglePlayPause: Image/Other - New isSlideshowPlayingIntent:", isSlideshowPlayingIntent);
            clearTimeout(imageTimer);
            console.debug("togglePlayPause (image/other): Cleared imageTimer (if any).");

            if (isSlideshowPlayingIntent) {
                const currentItemMime = mediaItems[currentIndex]?.mimetype?.toLowerCase() || '';
                const duration = (currentItemMime.startsWith('image/') || !currentItemMime || imageEl.src === brokenImagePath || imageEl.src === filePlaceholderPath) ?
                    DEFAULT_IMAGE_DURATION :
                    DEFAULT_IMAGE_DURATION / 2;
                imageTimer = setTimeout(nextMedia, duration);
                console.debug("togglePlayPause (image/other): Restarted imageTimer. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
            } else {
                console.debug("togglePlayPause (image/other): Not restarting imageTimer. isSlideshowPlayingIntent: " + isSlideshowPlayingIntent);
            }
        }
        // Visuals updated inside A/V logic on promise, or here for images
        if (!currentMediaElementForSeek) {
            updatePlayPauseVisuals();
        }
    }


    function handleVolumeChange() {
        if (!volumeControl) return;
        resetControlsHideTimer();
        const newVol = parseFloat(volumeControl.value);
        if (videoEl) videoEl.volume = newVol;
        if (audioEl) audioEl.volume = newVol;

        if (newVol > 0) {
            if (videoEl && videoEl.muted) videoEl.muted = false;
            if (audioEl && audioEl.muted) audioEl.muted = false;
            if (!hasUserInteractedForSound) hasUserInteractedForSound = true;
        } else {
            if (videoEl && !videoEl.muted) videoEl.muted = true;
            if (audioEl && !audioEl.muted) audioEl.muted = true;
        }
        updateVolumeIcon();
    }

    // === Fullscreen Core Logic & Event Handling (CHUNK 1 from your file - appears unchanged) ===
    function requestFullscreenOnElement(element) {
        if (!element) return;
        console.debug("Attempting to request fullscreen on:", element);
        if (element.requestFullscreen) { element.requestFullscreen().catch(err => console.error("FS Request Error:", err.message)); }
        else if (element.webkitRequestFullscreen) { element.webkitRequestFullscreen(); }
        else if (element.mozRequestFullScreen) { element.mozRequestFullScreen(); }
        else if (element.msRequestFullscreen) { element.msRequestFullscreen(); }
        else { console.warn("Fullscreen API not fully supported by this browser or on this element."); }
    }
    function exitFullscreenFromDocument() {
        console.debug("Attempting to exit fullscreen.");
        if (document.exitFullscreen) { document.exitFullscreen().catch(err => console.error("FS Exit Error:", err.message)); }
        else if (document.webkitExitFullscreen) { document.webkitExitFullscreen(); }
        else if (document.mozCancelFullScreen) { document.mozCancelFullScreen(); }
        else if (document.msExitFullscreen) { document.msExitFullscreen(); }
        else { console.warn("Exit Fullscreen API not fully supported by this browser."); }
    }
    function updateAppFullscreenUI() {
        const fsElement = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement;
        const isInAnyFullscreen = !!fsElement;
        const fullscreenIcon = fullscreenBtn ? fullscreenBtn.querySelector('i') : null;
        console.debug("updateAppFullscreenUI called. IsInAnyFullscreen:", isInAnyFullscreen, "FS Element:", fsElement);
        if (isInAnyFullscreen && fsElement === slideshowContainer) {
            slideshowContainer.classList.add('is-truly-fullscreen');
        } else {
            if (slideshowContainer) slideshowContainer.classList.remove('is-truly-fullscreen');
        }
        if (navbarEl) {
            if (isInAnyFullscreen) navbarEl.classList.add('navbar-hidden-true');
            else navbarEl.classList.remove('navbar-hidden-true');
        }
        if (returnLinkEl) {
            if (isInAnyFullscreen) returnLinkEl.classList.add('element-hidden-in-fullscreen');
            else returnLinkEl.classList.remove('element-hidden-in-fullscreen');
        }
        if (fullscreenIcon) {
            if (isInAnyFullscreen) {
                fullscreenIcon.classList.remove('bi-fullscreen'); fullscreenIcon.classList.add('bi-fullscreen-exit');
                if (fullscreenBtn) fullscreenBtn.title = "Exit Fullscreen (F or Esc)";
            } else {
                fullscreenIcon.classList.remove('bi-fullscreen-exit'); fullscreenIcon.classList.add('bi-fullscreen');
                if (fullscreenBtn) fullscreenBtn.title = "Toggle Fullscreen (F)";
            }
        }
        if (controlsContainerEl) {
            if (isInAnyFullscreen && (fsElement === videoEl || fsElement === audioEl)) {
                console.debug("Native media element fullscreened. Hiding custom controls overlay.");
                controlsContainerEl.classList.add('controls-truly-hidden');
                isAppInitiatedFullscreen = false;
            } else if (isInAnyFullscreen && fsElement === slideshowContainer) {
                console.debug("App container fullscreened. Custom controls managed by auto-hide.");
                controlsContainerEl.classList.remove('controls-truly-hidden');
            } else if (!isInAnyFullscreen) {
                console.debug("Exited all fullscreen. Ensuring custom controls are normally visible.");
                controlsContainerEl.classList.remove('controls-truly-hidden');
            }
        }
        if (!isInAnyFullscreen) {
            isAppInitiatedFullscreen = false;
        }
    }
    function handleFullscreenChange() {
        console.debug("handleFullscreenChange event triggered.");
        updateAppFullscreenUI();
        if (typeof resetControlsHideTimer === "function") {
            resetControlsHideTimer();
        }
    }
    if (fullscreenBtn && slideshowContainer) {
        fullscreenBtn.addEventListener('click', function() {
            console.debug("Fullscreen button clicked.");
            const fsElement = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement;
            if (!fsElement) {
                console.debug("Requesting fullscreen on slideshowContainer via button.");
                requestFullscreenOnElement(slideshowContainer);
                isAppInitiatedFullscreen = true;
            } else {
                console.debug("Attempting to exit fullscreen via button. Current FS element:", fsElement);
                exitFullscreenFromDocument();
                isAppInitiatedFullscreen = false;
            }
        });
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);
    setTimeout(handleFullscreenChange, 100); // Initial check
    // === CHUNK 1 END ===

    if (playPauseBtn) playPauseBtn.addEventListener('click', togglePlayPause);
    if (nextBtn) nextBtn.addEventListener('click', nextMedia);
    if (prevBtn) prevBtn.addEventListener('click', prevMedia);
    if (volumeControl) volumeControl.addEventListener('input', handleVolumeChange);

    if (mediaProgressBar) {
        mediaProgressBar.addEventListener('input', () => {
            if (currentMediaElementForSeek && !isNaN(currentMediaElementForSeek.duration) && isDraggingProgressBar) {
                if (timeDisplay) timeDisplay.textContent = `${formatTime(mediaProgressBar.value)}/${formatTime(currentMediaElementForSeek.duration)}`;
            }
            resetControlsHideTimer();
        });
        mediaProgressBar.addEventListener('change', () => {
            if (currentMediaElementForSeek && !isNaN(currentMediaElementForSeek.duration)) {
                currentMediaElementForSeek.currentTime = parseFloat(mediaProgressBar.value);
            }
            if (isDraggingProgressBar) isDraggingProgressBar = false;
            resetControlsHideTimer();
        });
        mediaProgressBar.addEventListener('mousedown', () => {
            if (currentMediaElementForSeek) isDraggingProgressBar = true;
            resetControlsHideTimer();
        });
        document.addEventListener('mouseup', () => { if (isDraggingProgressBar) isDraggingProgressBar = false; });
    }

    const onMediaEnded = (mediaElement) => {
        console.log(`onMediaEnded: ${mediaElement.id} ended. Current isSlideshowPlayingIntent: ${isSlideshowPlayingIntent}`);
        if (currentMediaElementForSeek === mediaElement) {
            if (mediaProgressBar && !isNaN(mediaElement.duration)) mediaProgressBar.value = mediaElement.duration;
            updateMediaTimelineUI();
        }
        // Use isSlideshowPlayingIntent to decide whether to advance
        if (isSlideshowPlayingIntent) {
            nextMedia();
        } else {
            updatePlayPauseVisuals(); // Ensure visuals reflect non-playing state
        }
    };

    document.addEventListener('keydown', (e) => {
        if (e.target.closest('input, textarea, select')) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        let handled = true;
        switch (e.key.toLowerCase()) {
            case ' ': togglePlayPause(); break;
            case 'arrowright': nextMedia(); break;
            case 'arrowleft': prevMedia(); break;
            case 'f': if (fullscreenBtn) { fullscreenBtn.click(); } break;
            default: handled = false;
        }
        if (handled) { e.preventDefault(); resetControlsHideTimer(); }
    });

    let touchstartX = 0, touchstartY = 0;
    if (slideshowContainer) {
        slideshowContainer.addEventListener('touchstart', e => { touchstartX = e.changedTouches[0].screenX; touchstartY = e.changedTouches[0].screenY; }, { passive: true });
        slideshowContainer.addEventListener('touchend', e => {
            const dX = e.changedTouches[0].screenX - touchstartX;
            const dY = e.changedTouches[0].screenY - touchstartY;
            if (Math.abs(dX) > Math.abs(dY) && Math.abs(dX) > 30) { // Horizontal swipe
                if (dX < 0) nextMedia(); else prevMedia();
                resetControlsHideTimer();
            }
        }, { passive: true });
    }

    function handleFirstUserGesture() {
        if (!hasUserInteractedForSound) {
            console.log("handleFirstUserGesture: First user gesture detected.");
            hasUserInteractedForSound = true;

            if (currentMediaElementForSeek && currentMediaElementForSeek.muted) {
                console.log("handleFirstUserGesture: Unmuting media:", currentMediaElementForSeek.id);
                currentMediaElementForSeek.muted = false;
                // If slideshow intent is play and media was paused due to lack of interaction, try playing
                if (isSlideshowPlayingIntent && currentMediaElementForSeek.paused) {
                    console.log("handleFirstUserGesture: Attempting to play previously blocked/muted media:", currentMediaElementForSeek.id);
                    currentMediaElementForSeek.play().catch(e => console.warn("handleFirstUserGesture: Delayed play failed:", e.message));
                }
            }
            updateVolumeIcon();
        }
    }
    ['click', 'keydown', 'touchstart'].forEach(evt => document.addEventListener(evt, handleFirstUserGesture, { once: true, capture: true }));

    // === Auto-Hide Controls Logic (CHUNK 2 from your file - appears unchanged) ===
    function showControls() {
        if (!controlsContainerEl) return;
        controlsContainerEl.classList.remove('controls-hidden');
        if (isAppInitiatedFullscreen) { // Only show navbar/return if app is fullscreen
            if (navbarEl) navbarEl.classList.remove('navbar-hidden');
            if (returnLinkEl) returnLinkEl.classList.remove('element-hidden-via-autohide');
        }
    }
    function hideControls() {
        if (document.activeElement &&
            (document.activeElement.closest('.controls-container') || document.activeElement.closest('.navbar'))) {
            if (typeof resetControlsHideTimer === "function") resetControlsHideTimer();
            return;
        }
        if (document.querySelector('.modal.show')) { // Don't hide if a modal is open
            if (typeof resetControlsHideTimer === "function") resetControlsHideTimer();
            return;
        }

        // Only hide if app initiated fullscreen
        if (isAppInitiatedFullscreen) {
            if (controlsContainerEl) controlsContainerEl.classList.add('controls-hidden');
            if (navbarEl) navbarEl.classList.add('navbar-hidden');
            if (returnLinkEl) returnLinkEl.classList.add('element-hidden-via-autohide');
        } else {
             // If not in app fullscreen, ensure controlsHideTimer is cleared so they don't hide
            clearTimeout(controlsHideTimer);
        }
    }
    function resetControlsHideTimer() {
        clearTimeout(controlsHideTimer);
        showControls(); // Always show on activity

        const currentItemIsImage = imageEl && imageEl.style.display !== 'none' && imageEl.classList.contains('media-active');
        // Check actual media state for A/V, or isSlideshowPlayingIntent for images
        const mediaIsEffectivelyPlayingOrDisplayed =
            (currentMediaElementForSeek && !currentMediaElementForSeek.paused && !currentMediaElementForSeek.ended) ||
            (currentItemIsImage && isSlideshowPlayingIntent);

        const isAnyModalVisible = !!document.querySelector('.modal.show');

        if (isAppInitiatedFullscreen && mediaIsEffectivelyPlayingOrDisplayed && !isAnyModalVisible) {
            controlsHideTimer = setTimeout(hideControls, CONTROLS_HIDE_DELAY);
        } else if (isAppInitiatedFullscreen && currentItemIsImage && !isSlideshowPlayingIntent && !isAnyModalVisible) { // Image paused
            controlsHideTimer = setTimeout(hideControls, CONTROLS_HIDE_DELAY + 2000); // Longer delay for paused image
        } else if (isAppInitiatedFullscreen && currentMediaElementForSeek && currentMediaElementForSeek.paused && !isAnyModalVisible) { // A/V paused
            controlsHideTimer = setTimeout(hideControls, CONTROLS_HIDE_DELAY); // Standard delay for paused A/V
        }
        // If not isAppInitiatedFullscreen, controls remain visible unless explicitly hidden elsewhere
    }
    // === CHUNK 2 END ===

    if (slideshowContainer) {
        slideshowContainer.addEventListener('mousemove', resetControlsHideTimer, { passive: true });
        slideshowContainer.addEventListener('click', (e) => {
            // Only toggle play/pause if click is on container/image/video itself, not controls
            if (e.target === imageEl || e.target === videoEl || e.target === slideshowContainer) {
                // Further check for native video controls click
                const isVideoControlsClick = currentMediaElementForSeek === videoEl &&
                    videoEl.controls && // Check if native controls are enabled (though typically we hide them)
                    e.offsetY > (videoEl.offsetHeight - 40); // Heuristic: click in bottom 40px

                if (!isVideoControlsClick) {
                    togglePlayPause();
                }
            }
            resetControlsHideTimer(); // Reset timer on any click within container
        });
    }
    [controlsContainerEl, navbarEl].forEach(el => {
        if (el) {
            el.addEventListener('mouseenter', () => clearTimeout(controlsHideTimer));
            el.addEventListener('mouseleave', resetControlsHideTimer);
        }
    });

    console.log("initSlideshow: Performing initial media load.");
    loadMedia(0);
    updateVolumeIcon(); // Set initial volume icon
    resetControlsHideTimer(); // Initial timer setup for controls visibility

    // Set initial volume for media elements after a slight delay, ensuring they are loaded
    if (volumeControl) {
        const setInitialVolumeSafe = (mediaEl) => {
            if (mediaEl && typeof mediaEl.volume !== 'undefined') {
                const setVol = () => mediaEl.volume = parseFloat(volumeControl.value);
                if (mediaEl.readyState >= mediaEl.HAVE_METADATA) { // HAVE_METADATA or higher
                    setVol();
                } else {
                    mediaEl.addEventListener('loadedmetadata', function onLd() {
                        setVol();
                        mediaEl.removeEventListener('loadedmetadata', onLd); // Clean up
                    }, { once: true });
                }
            }
            updateVolumeIcon(); // Update icon after setting volume
        };
        // Apply after initial media load and potential transition
        setTimeout(() => {
            if (currentMediaElementForSeek) {
                setInitialVolumeSafe(currentMediaElementForSeek);
            } else if (videoEl.src || audioEl.src) { // If an AV element has a src but isn't current (e.g. during init)
                setInitialVolumeSafe(videoEl.src ? videoEl : audioEl);
            } else {
                 updateVolumeIcon(); // Just ensure icon is correct if no media
            }
        }, MEDIA_TRANSITION_DURATION + 200); // Delay to allow media element to potentially load
    }

} // --- End of initSlideshow function ---
