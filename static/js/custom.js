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
    const CONTROLS_HIDE_DELAY = 3000;
    const MEDIA_TRANSITION_DURATION = 300;

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
        else if (videoEl.muted || audioEl.muted) isMuted = videoEl.muted || audioEl.muted;

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
            hideLoadingSpinner(); updateMediaTimelineUI(); updatePlayPauseVisuals(); updateVolumeIcon();
            if ((isPlayingStateForImages || !mediaElement.paused) && !mediaElement.classList.contains('media-active')) {
                 mediaElement.classList.add('media-active');
            }
        };
        mediaElement.ontimeupdate = () => { if (!isDraggingProgressBar) updateMediaTimelineUI(); };
        mediaElement.onplay = () => {
            console.debug("onplay:", mediaElement.id); isPlayingStateForImages = true;
            updatePlayPauseVisuals(); updateMediaTimelineUI(); resetControlsHideTimer();
        };
        mediaElement.onpause = () => {
            console.debug("onpause:", mediaElement.id); isPlayingStateForImages = false;
            updatePlayPauseVisuals(); updateMediaTimelineUI(); resetControlsHideTimer(); 
        };
        mediaElement.onended = () => { console.debug("onended:", mediaElement.id); onMediaEnded(mediaElement); };
        mediaElement.oncanplay = () => {
            console.debug("oncanplay:", mediaElement.id); hideLoadingSpinner(); 
            mediaElement.classList.add('media-active');
        };
    }

    function clearMediaElementSpecificListeners(mediaElement) {
        if (!mediaElement) return;
        mediaElement.onloadedmetadata = null; mediaElement.ontimeupdate = null;
        mediaElement.onplay = null; mediaElement.onpause = null; mediaElement.onended = null;
        mediaElement.oncanplay = null; mediaElement.onerror = null; mediaElement.onload = null;
    }

    function resetAndHideAllMediaElements() {
        console.debug("resetAndHideAllMediaElements: Hiding media elements.");
        [imageEl, videoEl, audioEl].forEach(el => el.classList.remove('media-active'));
        return new Promise(resolve => {
            setTimeout(() => {
                imageEl.style.display = 'none'; videoEl.style.display = 'none'; audioEl.style.display = 'none';
                if (currentMediaElementForSeek) {
                    currentMediaElementForSeek.pause();
                    if (currentMediaElementForSeek === videoEl) { videoEl.removeAttribute('src'); videoEl.load(); }
                    else if (currentMediaElementForSeek === audioEl) { audioEl.removeAttribute('src'); audioEl.load(); }
                    clearMediaElementSpecificListeners(currentMediaElementForSeek);
                } else { videoEl.removeAttribute('src'); videoEl.load(); audioEl.removeAttribute('src'); audioEl.load(); }
                imageEl.removeAttribute('src'); clearMediaElementSpecificListeners(imageEl);
                currentMediaElementForSeek = null;
                if (progressBarGroup) progressBarGroup.style.display = 'none'; resolve();
            }, MEDIA_TRANSITION_DURATION);
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
        clearTimeout(imageTimer); showLoadingSpinner(); await resetAndHideAllMediaElements();

        if (!item || !item.filepath) {
            console.error(`loadMedia: Item ${currentIndex} invalid.`, item); imageEl.onload = null; imageEl.onerror = null;
            imageEl.src = brokenImagePath; imageEl.alt = "Error: Invalid data"; imageEl.style.display = 'block';
            imageEl.classList.add('media-active'); hideLoadingSpinner();
            if (counterEl) counterEl.textContent = `${currentIndex + 1}/${mediaItems.length}`;
            if (isPlayingStateForImages) imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2);
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
            imageEl.onerror = () => { console.error("Img onerror:", mediaPath); hideLoadingSpinner();
                if (imageEl.src !== brokenImagePath) { imageEl.src = brokenImagePath; imageEl.alt = `Error: ${originalFilename}`; }
                imageEl.classList.add('media-active'); };
            imageEl.src = mediaPath; imageEl.alt = originalFilename; imageEl.style.display = 'block';
            if (isPlayingStateForImages) imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION);
        } else if (mimeType.startsWith('video/')) {
            videoEl.onerror = () => { console.error("Vid onerror:", mediaPath); hideLoadingSpinner();
                imageEl.src = videoPlaceholderPath; imageEl.alt = `Error: ${originalFilename}`; imageEl.style.display = 'block';
                imageEl.classList.add('media-active'); currentMediaElementForSeek = null; if(progressBarGroup) progressBarGroup.style.display = 'none';
                if (isPlayingStateForImages) imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2); };
            videoEl.src = mediaPath; videoEl.style.display = 'block'; currentMediaElementForSeek = videoEl; isAVMedia = true;
            setupMediaElementSpecificListeners(videoEl); videoEl.muted = !hasUserInteractedForSound;
            if (isPlayingStateForImages) videoEl.play().catch(e => console.warn(`Vid autoplay ${mediaPath}:`, e.message));
        } else if (mimeType.startsWith('audio/')) {
            audioEl.onerror = () => { console.error("Aud onerror:", mediaPath); hideLoadingSpinner();
                imageEl.src = audioPlaceholderPath; imageEl.alt = `Error: ${originalFilename}`; imageEl.style.display = 'block';
                imageEl.classList.add('media-active'); currentMediaElementForSeek = null; if(progressBarGroup) progressBarGroup.style.display = 'none';
                if (isPlayingStateForImages) imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2); };
            audioEl.src = mediaPath; audioEl.style.display = 'block'; currentMediaElementForSeek = audioEl; isAVMedia = true;
            setupMediaElementSpecificListeners(audioEl); audioEl.muted = !hasUserInteractedForSound;
            if (isPlayingStateForImages) audioEl.play().catch(e => console.warn(`Aud autoplay ${mediaPath}:`, e.message));
        } else {
            console.warn("Unsupported type:", mimeType); imageEl.onload = null; imageEl.onerror = null;
            imageEl.src = filePlaceholderPath; imageEl.alt = `Unsupported: ${originalFilename} (${mimeType})`;
            imageEl.style.display = 'block'; imageEl.classList.add('media-active'); hideLoadingSpinner();
            if (isPlayingStateForImages) imageTimer = setTimeout(nextMedia, DEFAULT_IMAGE_DURATION / 2);
        }
        if (isAVMedia && progressBarGroup && currentMediaElementForSeek) {
            progressBarGroup.style.display = 'flex';
            if (currentMediaElementForSeek.readyState >= currentMediaElementForSeek.HAVE_METADATA) updateMediaTimelineUI();
            else { if(mediaProgressBar){mediaProgressBar.max=100;mediaProgressBar.value=0;} if(timeDisplay)timeDisplay.textContent='0:00/0:00';}
        }
        updatePlayPauseVisuals(); updateVolumeIcon(); resetControlsHideTimer();
    }

    function updatePlayPauseVisuals() {
        if (!playPauseIcon || !playPauseBtn) return;
        let isPlaying = false;
        if (currentMediaElementForSeek) isPlaying = !currentMediaElementForSeek.paused && !currentMediaElementForSeek.ended;
        else if (imageEl.style.display !== 'none' && imageEl.classList.contains('media-active')) isPlaying = isPlayingStateForImages;
        playPauseIcon.className = isPlaying ? 'bi bi-pause-fill' : 'bi bi-play-fill';
        playPauseBtn.title = isPlaying ? "Pause (Spacebar)" : "Play (Spacebar)";
    }

    function nextMedia() { loadMedia((currentIndex + 1) % mediaItems.length); }
    function prevMedia() { loadMedia((currentIndex - 1 + mediaItems.length) % mediaItems.length); }

    function togglePlayPause() {
        resetControlsHideTimer(); const item = mediaItems[currentIndex]; if (!item) return;
        if (currentMediaElementForSeek) {
            if (currentMediaElementForSeek.muted && (currentMediaElementForSeek.paused || currentMediaElementForSeek.ended)) {
                currentMediaElementForSeek.muted = false; hasUserInteractedForSound = true; updateVolumeIcon(); }
            if (currentMediaElementForSeek.paused || currentMediaElementForSeek.ended) currentMediaElementForSeek.play().catch(e=>console.warn("Play fail:",e.message));
            else currentMediaElementForSeek.pause();
        } else {
            isPlayingStateForImages = !isPlayingStateForImages; clearTimeout(imageTimer);
            if (isPlayingStateForImages) {
                const mime = item.mimetype ? item.mimetype.toLowerCase() : '';
                imageTimer = setTimeout(nextMedia, mime.startsWith('image/') ? DEFAULT_IMAGE_DURATION : DEFAULT_IMAGE_DURATION / 2);
            }
            updatePlayPauseVisuals();
        }
    }
    
    function handleVolumeChange() {
        if (!volumeControl) return; resetControlsHideTimer(); const newVol = parseFloat(volumeControl.value);
        if (videoEl) videoEl.volume = newVol; if (audioEl) audioEl.volume = newVol;
        if (newVol > 0) {
            if (videoEl && videoEl.muted) videoEl.muted = false; if (audioEl && audioEl.muted) audioEl.muted = false;
            if (!hasUserInteractedForSound) hasUserInteractedForSound = true;
        } else { if (videoEl && !videoEl.muted) videoEl.muted = true; if (audioEl && !audioEl.muted) audioEl.muted = true; }
        updateVolumeIcon();
    }

    // --- Start: Your Original Working Fullscreen Logic ---
    function toggleFullscreen() {
        console.debug("toggleFullscreen called. Current fullscreenElement:", document.fullscreenElement);
        if (!document.fullscreenElement) {
            // Prefer to fullscreen the slideshowContainer itself, not documentElement, for better control
            if (slideshowContainer) {
                slideshowContainer.requestFullscreen().catch(err => console.error(`Slideshow container fullscreen error: ${err.message}`, err));
            } else {
                document.documentElement.requestFullscreen().catch(err => console.error(`Document fullscreen error: ${err.message}`, err));
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen().catch(err => console.error(`Exit fullscreen error: ${err.message}`, err));
            }
        }
        resetControlsHideTimer(); // Added to UX enhanced version
    }

    document.addEventListener('fullscreenchange', () => {
        const isAppFullscreen = !!document.fullscreenElement;
        const fullscreenedElement = document.fullscreenElement;
        console.debug("fullscreenchange event. Is app fullscreen:", isAppFullscreen, "Element:", fullscreenedElement);

        if (fullscreenBtn) {
            const icon = fullscreenBtn.querySelector('i');
            if (icon) {
                if (isAppFullscreen) { 
                    icon.classList.remove('bi-fullscreen'); icon.classList.add('bi-fullscreen-exit');
                    fullscreenBtn.title = "Exit Fullscreen (F or ESC)";
                } else { 
                    icon.classList.remove('bi-fullscreen-exit'); icon.classList.add('bi-fullscreen');
                    fullscreenBtn.title = "Toggle Fullscreen (F)";
                }
            }
        }

        if (navbarEl) navbarEl.style.display = isAppFullscreen ? 'none' : ''; 
        if (returnLinkEl) returnLinkEl.style.display = isAppFullscreen ? 'none' : '';
        
        if (controlsContainerEl) {
            if (isAppFullscreen) {
                // If the video/audio element ITSELF went native fullscreen (e.g. via its own controls)
                if (fullscreenedElement === videoEl || fullscreenedElement === audioEl) {
                    console.debug("Native media element fullscreen detected, hiding custom controls.");
                    controlsContainerEl.style.display = 'none';
                } else { // Our app's container is fullscreen
                    console.debug("App container fullscreen, ensuring custom controls are visible.");
                    controlsContainerEl.style.display = ''; 
                }
            } else { 
                console.debug("Exited all fullscreen, ensuring custom controls are visible (if media exists).");
                controlsContainerEl.style.display = (mediaItems && mediaItems.length > 0) ? '' : 'none';
            }
        }
        resetControlsHideTimer(); // Added to UX enhanced version
    });
    // --- End: Your Original Working Fullscreen Logic ---

    if (playPauseBtn) playPauseBtn.addEventListener('click', togglePlayPause);
    if (nextBtn) nextBtn.addEventListener('click', nextMedia);
    if (prevBtn) prevBtn.addEventListener('click', prevMedia);
    if (fullscreenBtn) fullscreenBtn.addEventListener('click', toggleFullscreen);
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
            updateMediaTimelineUI(); }
        if (isPlayingStateForImages) nextMedia(); else updatePlayPauseVisuals();
    };

    document.addEventListener('keydown', (e) => {
        if (e.target.closest('input, textarea, select')) return; // Simpler check for focused form elements
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        let handled = true;
        switch (e.key.toLowerCase()) {
            case ' ': togglePlayPause(); break;
            case 'arrowright': nextMedia(); break;
            case 'arrowleft': prevMedia(); break;
            case 'f': toggleFullscreen(); break;
            default: handled = false;
        }
        if (handled) { e.preventDefault(); resetControlsHideTimer(); }
    });

    let touchstartX = 0, touchstartY = 0;
    if (slideshowContainer) {
        slideshowContainer.addEventListener('touchstart', e=>{ touchstartX = e.changedTouches[0].screenX; touchstartY = e.changedTouches[0].screenY; }, {passive:true});
        slideshowContainer.addEventListener('touchend', e => {
            const dX = e.changedTouches[0].screenX - touchstartX; const dY = e.changedTouches[0].screenY - touchstartY;
            if (Math.abs(dX) > Math.abs(dY) && Math.abs(dX) > 30) {
                if (dX < 0) nextMedia(); else prevMedia(); resetControlsHideTimer(); }
        }, {passive:true});
    }

    function handleFirstUserGesture() {
        if (!hasUserInteractedForSound) {
            hasUserInteractedForSound = true; console.log("First user gesture, sound enabled.");
            if (currentMediaElementForSeek && currentMediaElementForSeek.muted) {
                currentMediaElementForSeek.muted = false;
                if (currentMediaElementForSeek.paused && isPlayingStateForImages) {
                    currentMediaElementForSeek.play().catch(e => console.warn("Delayed play fail:", e.message)); } }
            updateVolumeIcon(); }
    }
    ['click','keydown','touchstart'].forEach(evt=>document.addEventListener(evt,handleFirstUserGesture,{once:true,capture:true}));
    
    function showControls() {
        if (controlsContainerEl) controlsContainerEl.classList.remove('controls-hidden');
        if (navbarEl) navbarEl.classList.remove('navbar-hidden');
        const nativeMediaFS = document.fullscreenElement && (document.fullscreenElement === videoEl || document.fullscreenElement === audioEl);
        if (returnLinkEl) {
            if (document.fullscreenElement && !nativeMediaFS && document.fullscreenElement !== slideshowContainer) {
                returnLinkEl.style.display = 'none';
            } else if (!nativeMediaFS) {
                returnLinkEl.style.display = (!document.fullscreenElement || document.fullscreenElement === slideshowContainer) ? '' : 'none';
            } else { returnLinkEl.style.display = 'none'; } }
    }

    function hideControls() {
        if (isDraggingProgressBar || document.activeElement?.closest('.controls-container, .navbar')) {
            resetControlsHideTimer(); return; }
        const nativeMediaFSPaused = currentMediaElementForSeek?.paused && document.fullscreenElement === currentMediaElementForSeek;
        if (nativeMediaFSPaused) { resetControlsHideTimer(); return; }
        if (controlsContainerEl) controlsContainerEl.classList.add('controls-hidden');
        if (navbarEl) navbarEl.classList.add('navbar-hidden');
        if (returnLinkEl) returnLinkEl.style.display = 'none';
    }

    function resetControlsHideTimer() {
        clearTimeout(controlsHideTimer); showControls();
        const nativeMediaFS = document.fullscreenElement && (document.fullscreenElement === videoEl || document.fullscreenElement === audioEl);
        if ((isPlayingStateForImages || (!currentMediaElementForSeek && imageEl.style.display !== 'none' && imageEl.classList.contains('media-active'))) && !nativeMediaFS ) {
             controlsHideTimer = setTimeout(hideControls, CONTROLS_HIDE_DELAY); }
    }
    
    if (slideshowContainer) {
        slideshowContainer.addEventListener('mousemove', resetControlsHideTimer, { passive: true });
        slideshowContainer.addEventListener('click', (e) => {
            if (e.target === imageEl || e.target === videoEl || e.target === slideshowContainer) {
                const isVideoControlsClick = currentMediaElementForSeek === videoEl && videoEl.controls && e.offsetY > videoEl.offsetHeight - 40;
                if (!isVideoControlsClick) togglePlayPause();
            } resetControlsHideTimer(); });
    }
    [controlsContainerEl, navbarEl].forEach(el => { if (el) {
        el.addEventListener('mouseenter', () => clearTimeout(controlsHideTimer));
        el.addEventListener('mouseleave', resetControlsHideTimer); }});
    
    console.log("initSlideshow: Performing initial media load."); loadMedia(0);
    updateVolumeIcon(); resetControlsHideTimer();

    if (volumeControl) {
        const setInitialVolumeSafe = (mediaEl) => {
            if (mediaEl && typeof mediaEl.volume !== 'undefined') {
                if (mediaEl.readyState >= mediaEl.HAVE_METADATA) mediaEl.volume = parseFloat(volumeControl.value);
                else mediaEl.addEventListener('loadedmetadata', function l(){mediaEl.volume=parseFloat(volumeControl.value); mediaEl.removeEventListener('loadedmetadata',l);},{once:true});
            } updateVolumeIcon(); };
        setTimeout(() => {
            if (currentMediaElementForSeek) setInitialVolumeSafe(currentMediaElementForSeek);
            else updateVolumeIcon();
        }, MEDIA_TRANSITION_DURATION + 100);
    }
    
} // --- End of initSlideshow function ---
