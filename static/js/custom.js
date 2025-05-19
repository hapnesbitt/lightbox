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
            const feedback = this.closest('.card-body')?.querySelector('.form-text');
            if (this.files && this.files.length > 0 && feedback) {
                feedback.textContent = `${this.files.length} file(s) selected.`;
            } else if (feedback) {
                feedback.textContent = 'Allowed file types: Images, Videos, Audio, PDF';
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
    let isPlayingStateForImages = true; 
    let currentMediaElementForSeek = null;
    let isDraggingProgressBar = false;
    let hasUserInteractedForSound = false;
    let controlsHideTimer = null;
    let isAppInitiatedFullscreen = false; 
    const CONTROLS_HIDE_DELAY = 3000;
    const MEDIA_TRANSITION_DURATION = 300;
    let transitioningAway = false; 

    if (!mediaItems || mediaItems.length === 0) {
        console.warn('initSlideshow: No media items. Aborting.');
        if (slideshowContainer) slideshowContainer.innerHTML = '<p style="color: white; text-align: center; width:100%;">No media items to display.</p>';
        if (controlsContainerEl) controlsContainerEl.style.display = 'none';
        return;
    }
    console.log(`initSlideshow: Found ${mediaItems.length} media items.`);

    const showLoadingSpinner = () => { if (loadingSpinner) loadingSpinner.style.display = 'block'; };
    const hideLoadingSpinner = () => { if (loadingSpinner) loadingSpinner.style.display = 'none'; };

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
            mediaProgressBar.max = 100; mediaProgressBar.value = 0;
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
            if ((isPlayingStateForImages || !mediaElement.paused) && !mediaElement.classList.contains('media-active')) {
                mediaElement.classList.add('media-active');
            }
        };
        mediaElement.ontimeupdate = () => { if (!isDraggingProgressBar) updateMediaTimelineUI(); };

        mediaElement.onplay = () => {
            console.debug(`onplay: ${mediaElement.id}. Setting isPlayingStateForImages = true.`);
            isPlayingStateForImages = true; 
            updatePlayPauseVisuals();
            updateMediaTimelineUI();
            resetControlsHideTimer();
        };
        mediaElement.onpause = () => {
            console.debug(`onpause: ${mediaElement.id}. TransitioningAway: ${transitioningAway}`);
            if (!transitioningAway) { 
                console.debug("onpause: Not transitioning away. Setting isPlayingStateForImages = false.");
                isPlayingStateForImages = false; 
            } else {
                console.debug("onpause: Is transitioning away. isPlayingStateForImages remains:", isPlayingStateForImages);
            }
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
            if(progressBarGroup) progressBarGroup.style.display = 'none';
            if (isPlayingStateForImages) imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2); 
        };
    }

    function clearMediaElementSpecificListeners(mediaElement) {
        if (!mediaElement) return;
        mediaElement.onloadedmetadata = null; mediaElement.ontimeupdate = null;
        mediaElement.onplay = null; mediaElement.onpause = null; mediaElement.onended = null;
        mediaElement.oncanplay = null; mediaElement.onerror = null; mediaElement.onload = null;
    }

    function resetAndHideAllMediaElements() {
        console.debug("resetAndHideAllMediaElements: Hiding media elements. Current media:", currentMediaElementForSeek ? currentMediaElementForSeek.id : "none");
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
                console.error("loadMedia: mediaItems empty."); await resetAndHideAllMediaElements();
                if (slideshowContainer) slideshowContainer.innerHTML = '<p style="color: white; text-align: center; width:100%;">No media items.</p>';
                hideLoadingSpinner(); return;
            }
        }
        currentIndex = index; const item = mediaItems[currentIndex];
        console.log(`loadMedia: Item ${currentIndex + 1}/${mediaItems.length}`, JSON.stringify(item).substring(0, 200) + "...");
        clearTimeout(imageTimer); 
        console.debug("loadMedia: Cleared imageTimer (if any)."); // Log timer clearing
        showLoadingSpinner();

        await resetAndHideAllMediaElements(); 

        console.debug("loadMedia: Resetting transitioningAway to false after old media handled.");
        transitioningAway = false; 

        if (!item || !item.filepath) {
            console.error(`loadMedia: Item ${currentIndex} invalid.`, item);
            imageEl.onload = null; imageEl.onerror = null; 
            imageEl.src = brokenImagePath; imageEl.alt = "Error: Invalid data"; imageEl.style.display = 'block';
            imageEl.classList.add('media-active'); hideLoadingSpinner();
            if (counterEl) counterEl.textContent = `${currentIndex + 1}/${mediaItems.length}`;
            
            // For broken/invalid items, check isPlayingStateForImages before setting timer
            if (isPlayingStateForImages) {
                imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2);
                console.debug("loadMedia (broken item): Started imageTimer for " + (DEFAULT_IMAGE_DURATION / 2) + "ms. isPlayingStateForImages: " + isPlayingStateForImages);
            } else {
                console.debug("loadMedia (broken item): Not starting imageTimer. isPlayingStateForImages: " + isPlayingStateForImages);
            }
            updatePlayPauseVisuals(); return;
        }
        const mediaPath = item.filepath;
        const mimeType = item.mimetype ? item.mimetype.toLowerCase() : 'application/octet-stream';
        const originalFilename = item.original_filename || 'Unknown File';
        if (counterEl) counterEl.textContent = `${currentIndex + 1}/${mediaItems.length}`;
        if (downloadLink && typeof isPublicSlideshowView !== 'undefined' && !isPublicSlideshowView) {
            downloadLink.href = mediaPath; downloadLink.setAttribute('download', originalFilename);
            const dlC = downloadLink.closest('.download-container'); if (dlC) dlC.style.display = '';
        } else if (downloadLink) { const dlC = downloadLink.closest('.download-container'); if (dlC) dlC.style.display = 'none'; }

        let isAVMedia = false; console.debug(`loadMedia: Path: ${mediaPath}, Mime: ${mimeType}`);

        if (mimeType.startsWith('image/')) {
            imageEl.onload = () => { hideLoadingSpinner(); imageEl.classList.add('media-active'); console.debug("Img loaded:", mediaPath); };
            imageEl.onerror = () => {
                console.error("Img onerror:", mediaPath); hideLoadingSpinner();
                if (imageEl.src !== brokenImagePath) { imageEl.src = brokenImagePath; imageEl.alt = `Error loading: ${originalFilename}`; }
                imageEl.classList.add('media-active');
            };
            imageEl.src = mediaPath; imageEl.alt = originalFilename; imageEl.style.display = 'block';
            
            // CRITICAL: Logging for image timer
            if (isPlayingStateForImages) {
                imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION);
                console.debug("loadMedia (image): Started imageTimer for " + DEFAULT_IMAGE_DURATION + "ms. isPlayingStateForImages: " + isPlayingStateForImages);
            } else {
                console.debug("loadMedia (image): Not starting imageTimer as isPlayingStateForImages is false. isPlayingStateForImages: " + isPlayingStateForImages);
            }

        } else if (mimeType.startsWith('video/')) {
            videoEl.src = mediaPath; videoEl.style.display = 'block'; currentMediaElementForSeek = videoEl; isAVMedia = true;
            setupMediaElementSpecificListeners(videoEl); 
            videoEl.muted = !hasUserInteractedForSound;
            if (isPlayingStateForImages) {
                console.debug("loadMedia: Attempting autoplay for video", mediaPath, "as isPlayingStateForImages is true.");
                videoEl.play().catch(e => console.warn(`Vid autoplay ${mediaPath}:`, e.message));
            } else {
                console.debug("loadMedia: Not autoplaying video", mediaPath, "as isPlayingStateForImages is false.");
            }
        } else if (mimeType.startsWith('audio/')) {
            audioEl.src = mediaPath; audioEl.style.display = 'block'; currentMediaElementForSeek = audioEl; isAVMedia = true;
            setupMediaElementSpecificListeners(audioEl); 
            audioEl.muted = !hasUserInteractedForSound;
            if (isPlayingStateForImages) {
                console.debug("loadMedia: Attempting autoplay for audio", mediaPath, "as isPlayingStateForImages is true.");
                audioEl.play().catch(e => console.warn(`Aud autoplay ${mediaPath}:`, e.message));
            } else {
                console.debug("loadMedia: Not autoplaying audio", mediaPath, "as isPlayingStateForImages is false.");
            }
        } else { 
            console.warn("Unsupported type:", mimeType); imageEl.onload = null; imageEl.onerror = null;
            imageEl.src = filePlaceholderPath; imageEl.alt = `Unsupported: ${originalFilename} (${mimeType})`;
            imageEl.style.display = 'block'; imageEl.classList.add('media-active'); hideLoadingSpinner();
            // For unsupported items, check isPlayingStateForImages before setting timer
            if (isPlayingStateForImages) {
                imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2);
                 console.debug("loadMedia (unsupported item): Started imageTimer for " + (DEFAULT_IMAGE_DURATION / 2) + "ms. isPlayingStateForImages: " + isPlayingStateForImages);
            } else {
                console.debug("loadMedia (unsupported item): Not starting imageTimer. isPlayingStateForImages: " + isPlayingStateForImages);
            }
        }

        if (isAVMedia && progressBarGroup && currentMediaElementForSeek) {
            progressBarGroup.style.display = 'flex';
            if (currentMediaElementForSeek.readyState >= currentMediaElementForSeek.HAVE_METADATA) updateMediaTimelineUI();
            else { if(mediaProgressBar){mediaProgressBar.max=100;mediaProgressBar.value=0;} if(timeDisplay)timeDisplay.textContent='0:00/0:00';}
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
            isEffectivelyPlaying = isPlayingStateForImages;
        }
        playPauseIcon.className = isEffectivelyPlaying ? 'bi bi-pause-fill' : 'bi bi-play-fill';
        playPauseBtn.title = isEffectivelyPlaying ? "Pause (Spacebar)" : "Play (Spacebar)";
    }

    function nextMedia() { loadMedia((currentIndex + 1) % mediaItems.length); }
    function prevMedia() { loadMedia((currentIndex - 1 + mediaItems.length) % mediaItems.length); }

    function togglePlayPause() {
        console.log("togglePlayPause: Called. Current isPlayingStateForImages (intent):", isPlayingStateForImages);
        resetControlsHideTimer();
        const item = mediaItems[currentIndex]; if (!item) return;

        if (currentMediaElementForSeek) { 
            if (isPlayingStateForImages) {
                console.log("togglePlayPause: A/V - Intent was PLAY. Issuing PAUSE command.");
                currentMediaElementForSeek.pause();
            } else {
                console.log("togglePlayPause: A/V - Intent was PAUSE. Issuing PLAY command.");
                if (currentMediaElementForSeek.muted && !hasUserInteractedForSound) {
                    currentMediaElementForSeek.muted = false;
                    hasUserInteractedForSound = true; 
                    updateVolumeIcon();
                }
                currentMediaElementForSeek.play().catch(e => {
                    console.warn("togglePlayPause: A/V - Play command failed:", e.message);
                    if(isPlayingStateForImages){ 
                         isPlayingStateForImages = false; 
                    }
                    updatePlayPauseVisuals(); 
                });
            }
        } else { 
            isPlayingStateForImages = !isPlayingStateForImages; 
            console.log("togglePlayPause: Image/Other - New isPlayingStateForImages:", isPlayingStateForImages);
            clearTimeout(imageTimer);
            console.debug("togglePlayPause (image/other): Cleared imageTimer (if any).");

            if (isPlayingStateForImages) {
                const currentItem = mediaItems[currentIndex]; 
                const currentMime = currentItem && currentItem.mimetype ? currentItem.mimetype.toLowerCase() : '';
                const duration = (currentMime.startsWith('image/') || !currentMime || imageEl.src === brokenImagePath || imageEl.src === filePlaceholderPath) 
                                 ? DEFAULT_IMAGE_DURATION 
                                 : DEFAULT_IMAGE_DURATION / 2; // Shorter for non-images using this path (e.g. placeholders)
                
                imageTimer = setTimeout(nextMedia, duration);
                console.debug("togglePlayPause (image/other): Restarted imageTimer for " + duration + "ms. isPlayingStateForImages: " + isPlayingStateForImages);
            } else {
                 console.debug("togglePlayPause (image/other): Not restarting imageTimer as isPlayingStateForImages is now false. isPlayingStateForImages: " + isPlayingStateForImages);
            }
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

    // === CHUNK 1 START: New Fullscreen Core Logic & Event Handling ===
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
            if(slideshowContainer) slideshowContainer.classList.remove('is-truly-fullscreen');
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
                if(fullscreenBtn) fullscreenBtn.title = "Exit Fullscreen (F or Esc)";
            } else {
                fullscreenIcon.classList.remove('bi-fullscreen-exit'); fullscreenIcon.classList.add('bi-fullscreen');
                if(fullscreenBtn) fullscreenBtn.title = "Toggle Fullscreen (F)";
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
    setTimeout(handleFullscreenChange, 100);
    // === CHUNK 1 END ===

    if (playPauseBtn) playPauseBtn.addEventListener('click', togglePlayPause);
    if (nextBtn) nextBtn.addEventListener('click', nextMedia);
    if (prevBtn) prevBtn.addEventListener('click', prevMedia);
    if (volumeControl) volumeControl.addEventListener('input', handleVolumeChange);

    if (mediaProgressBar) {
        mediaProgressBar.addEventListener('input', () => {
            if (currentMediaElementForSeek && !isNaN(currentMediaElementForSeek.duration) && isDraggingProgressBar) {
                if (timeDisplay) timeDisplay.textContent = `${formatTime(mediaProgressBar.value)}/${formatTime(currentMediaElementForSeek.duration)}`;
            } resetControlsHideTimer(); });
        mediaProgressBar.addEventListener('change', () => {
            if (currentMediaElementForSeek && !isNaN(currentMediaElementForSeek.duration)) {
                currentMediaElementForSeek.currentTime = parseFloat(mediaProgressBar.value); }
            if (isDraggingProgressBar) isDraggingProgressBar = false; resetControlsHideTimer(); });
        mediaProgressBar.addEventListener('mousedown', () => {
            if (currentMediaElementForSeek) isDraggingProgressBar = true; resetControlsHideTimer(); });
        document.addEventListener('mouseup', () => { if (isDraggingProgressBar) isDraggingProgressBar = false; }); 
    }

    const onMediaEnded = (mediaElement) => {
        console.log(`onMediaEnded: ${mediaElement.id} ended.`);
        if (currentMediaElementForSeek === mediaElement) {
            if (mediaProgressBar && !isNaN(mediaElement.duration)) mediaProgressBar.value = mediaElement.duration;
            updateMediaTimelineUI();
        }
        if (isPlayingStateForImages) {
            nextMedia();
        } else {
            updatePlayPauseVisuals();
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
        slideshowContainer.addEventListener('touchstart', e => { touchstartX = e.changedTouches[0].screenX; touchstartY = e.changedTouches[0].screenY; }, {passive:true});
        slideshowContainer.addEventListener('touchend', e => {
            const dX = e.changedTouches[0].screenX - touchstartX; const dY = e.changedTouches[0].screenY - touchstartY;
            if (Math.abs(dX) > Math.abs(dY) && Math.abs(dX) > 30) { 
                if (dX < 0) nextMedia(); else prevMedia();
                resetControlsHideTimer();
            }
        }, {passive:true});
    }

    function handleFirstUserGesture() {
        if (!hasUserInteractedForSound) {
            console.log("handleFirstUserGesture: First user gesture detected.");
            hasUserInteractedForSound = true; 

            if (currentMediaElementForSeek && currentMediaElementForSeek.muted) {
                console.log("handleFirstUserGesture: Unmuting media:", currentMediaElementForSeek.id);
                currentMediaElementForSeek.muted = false;
                if (isPlayingStateForImages && currentMediaElementForSeek.paused) {
                    console.log("handleFirstUserGesture: Attempting to play previously blocked/muted media:", currentMediaElementForSeek.id);
                    currentMediaElementForSeek.play().catch(e => console.warn("handleFirstUserGesture: Delayed play failed:", e.message));
                }
            }
            updateVolumeIcon(); 
        }
    }
    ['click','keydown','touchstart'].forEach(evt=>document.addEventListener(evt,handleFirstUserGesture,{once:true,capture:true}));

    // === CHUNK 2 START: Modified Auto-Hide Controls Logic ===
    function showControls() {
        if (!controlsContainerEl) return;
        controlsContainerEl.classList.remove('controls-hidden');
        if (isAppInitiatedFullscreen) {
            if (navbarEl) navbarEl.classList.remove('navbar-hidden');
            if (returnLinkEl) returnLinkEl.classList.remove('element-hidden-via-autohide');
        }
    }
    function hideControls() {
        if (document.activeElement &&
            (document.activeElement.closest('.controls-container') || document.activeElement.closest('.navbar')) ) {
            if (typeof resetControlsHideTimer === "function") resetControlsHideTimer();
            return;
        }
        if (document.querySelector('.modal.show')) {
            if (typeof resetControlsHideTimer === "function") resetControlsHideTimer();
            return;
        }
        if (isAppInitiatedFullscreen) {
            if (controlsContainerEl) controlsContainerEl.classList.add('controls-hidden');
            if (navbarEl) navbarEl.classList.add('navbar-hidden');
            if (returnLinkEl) returnLinkEl.classList.add('element-hidden-via-autohide');
        } else {
            clearTimeout(controlsHideTimer);
        }
    }
    function resetControlsHideTimer() {
        clearTimeout(controlsHideTimer);
        showControls();
        const currentItemIsImage = imageEl && imageEl.style.display !== 'none' && imageEl.classList.contains('media-active');
        const mediaIsEffectivelyPlayingOrDisplayed =
            (currentMediaElementForSeek && !currentMediaElementForSeek.paused && !currentMediaElementForSeek.ended) ||
            (currentItemIsImage && isPlayingStateForImages);
        const isAnyModalVisible = !!document.querySelector('.modal.show');
        if (isAppInitiatedFullscreen && mediaIsEffectivelyPlayingOrDisplayed && !isAnyModalVisible) {
            controlsHideTimer = setTimeout(hideControls, CONTROLS_HIDE_DELAY);
        } else if (isAppInitiatedFullscreen && currentItemIsImage && !isPlayingStateForImages && !isAnyModalVisible) {
            controlsHideTimer = setTimeout(hideControls, CONTROLS_HIDE_DELAY + 2000);
        } else if (isAppInitiatedFullscreen && currentMediaElementForSeek && currentMediaElementForSeek.paused && !isAnyModalVisible) {
            controlsHideTimer = setTimeout(hideControls, CONTROLS_HIDE_DELAY);
        }
    }
    // === CHUNK 2 END ===

    if (slideshowContainer) {
        slideshowContainer.addEventListener('mousemove', resetControlsHideTimer, { passive: true });
        slideshowContainer.addEventListener('click', (e) => {
            if (e.target === imageEl || e.target === videoEl || e.target === slideshowContainer) {
                const isVideoControlsClick = currentMediaElementForSeek === videoEl &&
                                             videoEl.controls && 
                                             e.offsetY > (videoEl.offsetHeight - 40); 
                if (!isVideoControlsClick) {
                    togglePlayPause();
                }
            }
            resetControlsHideTimer(); 
        });
    }
    [controlsContainerEl, navbarEl].forEach(el => { if (el) {
        el.addEventListener('mouseenter', () => clearTimeout(controlsHideTimer));
        el.addEventListener('mouseleave', resetControlsHideTimer); }});

    console.log("initSlideshow: Performing initial media load.");
    loadMedia(0); 
    updateVolumeIcon(); 
    resetControlsHideTimer(); 

    if (volumeControl) { 
        const setInitialVolumeSafe = (mediaEl) => {
            if (mediaEl && typeof mediaEl.volume !== 'undefined') {
                const setVol = () => mediaEl.volume = parseFloat(volumeControl.value);
                if (mediaEl.readyState >= mediaEl.HAVE_METADATA) {
                    setVol();
                } else {
                    mediaEl.addEventListener('loadedmetadata', function onLd(){
                        setVol();
                        mediaEl.removeEventListener('loadedmetadata', onLd);
                    },{once:true});
                }
            }
            updateVolumeIcon(); 
        };
        setTimeout(() => {
            if (currentMediaElementForSeek) {
                setInitialVolumeSafe(currentMediaElementForSeek);
            } else if (videoEl.src || audioEl.src) { 
                setInitialVolumeSafe(videoEl.src ? videoEl : audioEl);
            } else {
                 updateVolumeIcon(); 
            }
        }, MEDIA_TRANSITION_DURATION + 200); 
    }

} // --- End of initSlideshow function ---
