        // SPA state management
        let initialViewContent = null;
        const appHistory = [];

        function getCurrentState() {
            const mainContent = document.querySelector('.main-scrollable-area');
            const playlistView = mainContent.querySelector('.playlist-detail-container');
            if (playlistView) {
                return { type: 'playlist', id: playlistView.dataset.playlistId };
            }
            return { type: 'featured' };
        }

        function appNavigateTo(page, data, pushHistory = true) {
            if (page === 'featured') {
                navigatePage('/');
            } else if (page === 'playlist') {
                navigatePage(`/playlist/${data.id}/`, pushHistory);
            }

            document.querySelector('.main-scrollable-area').scrollTop = 0;
        }

        function updateSidebarHighlight(page, data) {
            document.querySelectorAll('.sidebar-pill').forEach(elp => elp.classList.remove('active'));
            if (page === 'featured') {
                const featured = document.querySelector('nav .sidebar-pill[href*="index"], nav .sidebar-pill[href="/"]');
                if (featured) featured.classList.add('active');
            } else if (page === 'playlist' && data && data.id) {
                const selector = `nav .sidebar-pill[href*="${data.id}"], #sidebar-playlists .sidebar-pill[data-playlist-id="${data.id}"]`;
                const link = document.querySelector(selector);
                if (link) link.classList.add('active');
            }
        }
        function renderPlaylistDetailView(playlistId, incrementView = true, pushState = true, skipAnimation = false) {
            navigatePage(`/playlist/${playlistId}/`, pushState, skipAnimation);
        }

        window.playAllSongs = function(songs) {
            if (!songs || songs.length === 0) {
                showHubToast("No songs to play!");
                return;
            }
            
            // 1. Clear and Rebuild Queue
            window.playerQueue = [];
            songs.forEach(s => {
                window.playerQueue.push({
                    url: s.url,
                    title: s.title,
                    artist: s.artist,
                    cover: s.cover,
                    id: s.id,
                    album: s.album || 'Unknown',
                    isLiked: s.isLiked || false,
                    duration: s.duration || '00:00',
                    song_type: s.song_type || s.songType || ''
                });
            });

            // 2. Set index and play first
            window.queueIndex = 0;
            const target = window.playerQueue[0];
            
            const targetAbsUrl = new URL(target.url, window.location.origin).href;
            const currentAbsUrl = currentAudio.src ? new URL(currentAudio.src, window.location.origin).href : '';
            const isSameSong = (targetAbsUrl === currentAbsUrl);

            // If it's the same song, keep current play/pause state but restart from 0
            const shouldForceAutoPlay = isSameSong ? !currentAudio.paused : true;

            // loadAndPlay handles internal state, history and UI sync
            loadAndPlay(target.url, target.title, target.artist, target.cover, target.id, shouldForceAutoPlay, target.album, true);
            
            updateQueueUI();
        };

        function playPlaylistSongs(songIds) {
            // Check if this is a list of objects (new way) or just IDs (legacy)
            if (songIds && songIds.length > 0) {
                if (typeof songIds[0] === 'object') {
                    window.playAllSongs(songIds);
                } else {
                    // Legacy check: if we only have IDs, we just play the first one for now
                    if (typeof playSong === 'function') {
                        playSong(songIds[0]);
                        showHubToast("Starting playlist...");
                    }
                }
            }
        }

        window.playPlaylistById = async function(playlistId, sort = 'default') {
            if (!playlistId) return;
            showHubToast("Loading playlist...");
            
            try {
                const sortParam = sort && sort !== 'default' ? `?sort=${encodeURIComponent(sort)}` : '';
                const response = await fetch(`/api/playlist-details/${playlistId}/${sortParam}`);
                const data = await response.json();
                
                if (data.success && data.playlist && data.playlist.songs && data.playlist.songs.length > 0) {
                    const songs = data.playlist.songs.map(s => ({
                        url: s.file_url,
                        title: s.title,
                        artist: s.artist,
                        cover: s.cover,
                        id: s.id,
                        album: s.album,
                        isLiked: s.is_liked
                    }));
                    window.playAllSongs(songs);
                    showHubToast(`Playing: ${data.playlist.name}`);
                } else {
                    showHubToast("Playlist is empty!");
                }
            } catch (err) {
                console.error("Error playing playlist:", err);
                showHubToast("Failed to load playlist.");
            }
        };

        function downloadSongPlaylist() {
            showHubToast("Downloading playlist...");
        }

        function downloadSong(url, name) {
            const absoluteUrl = new URL(url, window.location.origin).href;
            showHubToast("Starting download...");
            
            fetch(absoluteUrl)
                .then(resp => {
                    if (!resp.ok) throw new Error('Network error');
                    return resp.blob();
                })
                .then(blob => {
                    const blobUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.style.display = 'none';
                    a.href = blobUrl;
                    a.setAttribute('data-skip-spa', 'true');
                    const filename = name.toLowerCase().endsWith('.mp3') ? name : name + '.mp3';
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    
                    setTimeout(() => {
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(blobUrl);
                    }, 1000); // More generous time for browser to start
                    
                    showHubToast("Download started!");
                })
                .catch(err => {
                    console.error("Download failed:", err);
                    showHubToast("Retrying via direct link...");
                    const a = document.createElement('a');
                    a.href = absoluteUrl;
                    a.download = name;
                    a.target = '_blank';
                    a.setAttribute('data-skip-spa', 'true');
                    a.click();
                });
        }

        function removeFromPlaylist(playlistId, songId) {
            if (playlistId === 'favorites' || playlistId === 'recent') {
                showHubToast("Cannot remove from this playlist.");
                return;
            }
            const fd = new FormData();
            fd.append('playlist_id', playlistId);
            fd.append('song_id', songId);
            fd.append('csrfmiddlewaretoken', getCookie('csrftoken'));
            fetch('/api/remove-from-playlist/', { method: 'POST', body: fd })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showHubToast("Removed from playlist.");
                        renderPlaylistDetailView(playlistId, false);
                    } else {
                        showHubToast(data.error || "Failed to remove song.");
                    }
                });
        }

        document.addEventListener('DOMContentLoaded', function () {
            const overlay = document.getElementById('authModalOverlay');
            const btnOpenLogin = document.getElementById('openLoginModal');
            const btnOpenReg = document.getElementById('openRegisterModal'); // if any
            const btnClose = document.getElementById('closeAuthModal');

            const tabLogin = document.getElementById('tabBtnLogin');
            const tabReg = document.getElementById('tabBtnRegister');
            const formLogin = document.getElementById('modalLoginForm');
            const formReg = document.getElementById('modalRegisterForm');

            window.openAuthModal = function(mode) {
                if (!overlay) return;
                overlay.style.display = 'flex';
                if (mode === 'register') {
                    showRegister();
                } else {
                    showLogin();
                }
            };

            const openModal = window.openAuthModal;

            function closeModal() {
                if (overlay) overlay.style.display = 'none';
            }

            function showLogin(e) {
                if (e) e.preventDefault();
                tabLogin.classList.add('active');
                tabLogin.style.color = '#00C78A';
                tabReg.classList.remove('active');
                tabReg.style.color = 'rgba(255,255,255,0.6)';
                formLogin.style.display = 'block';
                formReg.style.display = 'none';
            }

            function showRegister(e) {
                if (e) e.preventDefault();
                tabReg.classList.add('active');
                tabReg.style.color = '#00C78A';
                tabLogin.classList.remove('active');
                tabLogin.style.color = 'rgba(255,255,255,0.6)';
                formReg.style.display = 'block';
                formLogin.style.display = 'none';
            }

            if (btnOpenLogin) btnOpenLogin.addEventListener('click', function(e) { e.preventDefault(); openModal('login'); });
            if (btnOpenReg) btnOpenReg.addEventListener('click', function(e) { e.preventDefault(); openModal('register'); });
            if (btnClose) btnClose.addEventListener('click', closeModal);

            if (tabLogin) tabLogin.addEventListener('click', showLogin);
            if (tabReg) tabReg.addEventListener('click', showRegister);

            // Suppress entrance animation and preserve scroll on login/register form submit
            var modalLoginForm = document.getElementById('modalOverlayLoginForm');
            if (modalLoginForm) {
                modalLoginForm.addEventListener('submit', function(e) {
                    e.preventDefault();
                    
                    const loginBtn = document.getElementById('login');
                    const errorMsg = document.getElementById('loginErrorMessage');
                    const originalBtnValue = loginBtn.value;
                    
                    // Visual feedback
                    loginBtn.value = 'Signing in...';
                    loginBtn.disabled = true;
                    errorMsg.style.display = 'none';
                    
                    var mainArea = document.querySelector('.main-scrollable-area');
                    if (mainArea) sessionStorage.setItem('restore_scroll', mainArea.scrollTop);

                    const formData = new FormData(this);
                    fetch(this.action, {
                        method: 'POST',
                        body: formData,
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            window.location.reload();
                        } else {
                            loginBtn.value = originalBtnValue;
                            loginBtn.disabled = false;
                            errorMsg.textContent = data.error;
                            errorMsg.style.display = 'block';
                            
                            // Subtle shake animation if possible, or just focus
                            document.getElementById('password').value = '';
                            document.getElementById('password').focus();
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        loginBtn.value = originalBtnValue;
                        loginBtn.disabled = false;
                        errorMsg.textContent = 'Connection error. Please try again.';
                        errorMsg.style.display = 'block';
                    });
                });
            }
            var modalRegForm = document.getElementById('modalOverlayRegisterForm');
            if (modalRegForm) {
                modalRegForm.addEventListener('submit', function() {
                    var mainArea = document.querySelector('.main-scrollable-area');
                    if (mainArea) sessionStorage.setItem('restore_scroll', mainArea.scrollTop);
                });
            }

            if (overlay) {
                overlay.addEventListener('mousedown', function(e) {
                    if (e.target === overlay) closeModal();
                });
            }
        });

        // --- Global Interaction System ---
        let hubToastTimer = null;
        function hideHubToast() {
            const toast = document.getElementById('hub-toast');
            if (!toast) return;
            toast.classList.remove('show');
            if (hubToastTimer) {
                clearTimeout(hubToastTimer);
                hubToastTimer = null;
            }
        }

        function showHubToast(message) {
            const toast = document.getElementById('hub-toast');
            if (toast) {
                toast.textContent = message;
                toast.classList.add('show');
                if (hubToastTimer) clearTimeout(hubToastTimer);
                hubToastTimer = setTimeout(hideHubToast, 3000);
            }
        }

        window.hideHubToast = hideHubToast;
        document.addEventListener('pointerdown', hideHubToast, true);

        // 1. Toggle Like Behavior
        function toggleLike(songId, el) {
            if (!window.AURORA || !window.AURORA.isAuthenticated) {
                showHubToast("Please login first!");
                return;
            }
            if (!songId) return;
            const fd = new FormData();
            fd.append('song_id', songId);
            fd.append('csrfmiddlewaretoken', getCookie('csrftoken'));

            fetch('/api/toggle-favorite/', { method: 'POST', body: fd })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        // Global sync: update ALL heart icons on the page for this song
                        document.querySelectorAll(`[data-song-id="${songId}"]`).forEach(heart => {
                            if (heart.classList.contains('song-row-heart')) {
                                if (data.is_liked) {
                                    heart.classList.add('is-liked');
                                    heart.setAttribute('data-song-liked', 'true');
                                } else {
                                    heart.classList.remove('is-liked');
                                    heart.setAttribute('data-song-liked', 'false');
                                }
                            }
                        });

                        // Update Player Bar Count explicitly
                        const pCount = document.getElementById('player-like-count');
                        if (pCount && data.likes_count !== undefined) {
                            pCount.textContent = data.likes_count.toLocaleString();
                        }

                        // Sync queue state (robust string comparison)
                        if (window.playerQueue) {
                            const songInQueue = window.playerQueue.find(s => s.id.toString() === songId.toString());
                            if (songInQueue) {
                                songInQueue.isLiked = data.is_liked;
                                updateQueueUI();
                            }
                        }

                        showHubToast(data.is_liked ? "Added to Favorites!" : "Removed from Favorites.");

                        // 如果在 favorites 歌单页且刚刚取消了喜欢，自动刷新页面移除该歌曲
                        if (!data.is_liked) {
                            const playlistContainer = document.querySelector('.playlist-detail-container');
                            if (playlistContainer && playlistContainer.dataset.playlistId === 'favorites') {
                                navigatePage('/playlist/favorites/', false);
                            }
                        }
                    } else if (data.status === 'unauthorized' || data.error === 'unauthorized') {
                        showHubToast("Please login first!");
                    }
                });
        }

        // 2. Playlist Modal Management
        window.currentSongId = null;

        function openPlaylistModal(songId) {
            const overlay = document.getElementById('playlist-modal-overlay');
            const listContainer = document.getElementById('user-playlists-list');

            if (!songId) {
                showHubToast("Select a song first!");
                return;
            }

            overlay.style.display = 'flex';
            listContainer.innerHTML = '<div style="text-align:center; padding: 2em; opacity: 0.5;">Loading playlists...</div>';

            fetch('/api/playlists/')
                .then(r => {
                    if (r.status === 401) {
                        showHubToast("Please login first!");
                        overlay.style.display = 'none';
                        throw new Error('Unauthorized');
                    }
                    return r.json();
                })
                .then(data => {
                    listContainer.innerHTML = '';
                    if (data.playlists) {
                        data.playlists.forEach(p => {
                            const item = document.createElement('div');
                            item.className = 'playlist-item';
                            item.innerHTML = `
                                <div class="playlist-item-img" style="position: relative;">
                                    <img src="${p.cover}" style="width:100%; height:100%; object-fit:cover;" onerror="this.onerror=null; this.src='/media/playlists/default_playlist.png'">
                                    ${p.is_private ? `
                                    <div class="private-lock-overlay">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                                            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                                            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                                        </svg>
                                    </div>` : ''}
                                </div>
                                <div class="playlist-item-info">
                                    <div class="playlist-item-name">${p.name}</div>
                                    <div class="playlist-item-count">${p.count} tracks</div>
                                </div>
                    `;
                            item.onclick = () => addToPlaylist(p.id, songId);
                            listContainer.appendChild(item);
                        });
                    }
                }).catch(err => console.log(err));
        }
        
        // Ensure compatibility for detail pages
        window.triggerAddToPlaylist = openPlaylistModal;

        window.triggerAddMultipleToPlaylist = function(ids) {
            if (!ids || ids.length === 0) {
                showHubToast("Select songs first!");
                return;
            }
            openPlaylistModal(ids.join(','));
        };

        function addToPlaylist(playlistId, songId) {
            const targetSongId = songId || window.currentSongId;
            if (!targetSongId) return;

            const fd = new FormData();
            fd.append('song_id', targetSongId);
            fd.append('playlist_id', playlistId);
            fd.append('csrfmiddlewaretoken', getCookie('csrftoken'));

            fetch('/api/add-to-playlist/', { method: 'POST', body: fd })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        if (data.already_exists) {
                            const msg = data.multi 
                                ? `All songs already in ${data.playlist_name}` 
                                : `Song already in ${data.playlist_name}`;
                            showHubToast(msg);
                        } else {
                            showHubToast(`Added to ${data.playlist_name}`);
                        }
                        document.getElementById('playlist-modal-overlay').style.display = 'none';
                        loadSidebarPlaylists();

                        // Auto-refresh if current view is the playlist that was just updated
                        const currentPath = window.location.pathname;
                        const isSamePlaylist = currentPath.includes(`/playlist/${playlistId}/`);
                        const isFavoritesTab = playlistId === 'favorites' && currentPath.includes('/library/');
                        
                        if (isSamePlaylist || isFavoritesTab) {
                            if (typeof navigatePage === 'function') {
                                navigatePage(window.location.href, false);
                            }
                        }
                    } else {
                        showHubToast(data.error || "Failed to add");
                    }
                });
        }

        function createPlaylist() {
            const titleInput = document.getElementById('new-playlist-title');
            const title = titleInput.value.trim();
            const isPrivate = document.getElementById('is-private-playlist').checked;
            if (!title) return;

            const fd = new FormData();
            fd.append('name', title);
            fd.append('is_private', isPrivate);
            fd.append('csrfmiddlewaretoken', getCookie('csrftoken'));

            fetch('/api/create-playlist/', { method: 'POST', body: fd })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showHubToast("Playlist created");
                        document.getElementById('create-playlist-overlay').style.display = 'none';
                        titleInput.value = '';
                        document.getElementById('is-private-playlist').checked = false;
                        loadSidebarPlaylists();
                    } else {
                        showHubToast(data.error || "Creation failed");
                    }
                });
        }

        function loadSidebarPlaylists() {
            const sidebarContainer = document.getElementById('sidebar-playlists');
            const countDisplay = document.getElementById('sidebar-created-count');
            if (!sidebarContainer) return;

            fetch('/api/playlists/')
                .then(r => r.json())
                .then(data => {
                    if (data.playlists) {
                        const createdOnly = data.playlists.filter(p => p.id !== 'favorites');
                        sidebarContainer.innerHTML = '';
                        if (countDisplay) countDisplay.textContent = createdOnly.length;

                        if (createdOnly.length === 0) {
                            // No playlists - keep it clean
                            sidebarContainer.innerHTML = '';
                            return;
                        }

                        createdOnly.forEach(p => {
                            const link = document.createElement('a');
                            link.className = 'sidebar-pill flex-align';
                            link.style.textDecoration = 'none';
                            link.setAttribute('href', `/playlist/${p.id}/`);
                            link.setAttribute('data-playlist-id', p.id);
                            link.setAttribute('draggable', 'true');

                            link.innerHTML = `<div style="width: 18px; height: 18px; border-radius: 3px; overflow: hidden; flex-shrink: 0; background: rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; position: relative;">
                                <img src="${p.cover}" style="width: 100%; height: 100%; object-fit: cover; display: block;" onerror="this.onerror=null; this.src='/media/playlists/default_playlist.png'">
                                ${p.is_private ? `
                                <div class="private-lock-overlay" style="background: rgba(0,0,0,0.35);">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                                        <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                                    </svg>
                                </div>` : ''}
                            </div><span>${p.name}</span>`;
                            sidebarContainer.appendChild(link);
                        });
                        initSidebarPlaylistDragSort('sidebar-playlists', '/api/update-sidebar-playlist-order/');
                        syncSidebarWithURL(window.location.href);
                    }
                });
        }

        function saveSidebarPlaylistOrder(containerId, endpoint) {
            const sidebarContainer = document.getElementById(containerId);
            if (!sidebarContainer) return;
            const playlistIds = Array.from(sidebarContainer.querySelectorAll('.sidebar-pill[data-playlist-id]'))
                .map(el => el.getAttribute('data-playlist-id'))
                .filter(Boolean);

            fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ playlist_ids: playlistIds })
            }).catch(err => {
                console.error('Failed to save sidebar playlist order:', err);
            });
        }

        function initSidebarPlaylistDragSort(containerId, endpoint) {
            const sidebarContainer = document.getElementById(containerId);
            if (!sidebarContainer || sidebarContainer.dataset.dragSortReady === 'true') return;

            let draggedItem = null;
            let didDrag = false;

            sidebarContainer.addEventListener('dragstart', (event) => {
                const item = event.target.closest('.sidebar-pill[data-playlist-id]');
                if (!item) return;
                draggedItem = item;
                didDrag = false;
                item.classList.add('sidebar-dragging');
                event.dataTransfer.effectAllowed = 'move';
                event.dataTransfer.setData('text/plain', item.getAttribute('data-playlist-id'));
            });

            sidebarContainer.addEventListener('dragover', (event) => {
                if (!draggedItem) return;
                const target = event.target.closest('.sidebar-pill[data-playlist-id]');
                if (!target || target === draggedItem || target.parentElement !== sidebarContainer) return;
                event.preventDefault();
                didDrag = true;
                const targetRect = target.getBoundingClientRect();
                const insertAfter = event.clientY > targetRect.top + targetRect.height / 2;
                sidebarContainer.insertBefore(draggedItem, insertAfter ? target.nextSibling : target);
            });

            sidebarContainer.addEventListener('drop', (event) => {
                if (!draggedItem) return;
                event.preventDefault();
                didDrag = true;
                saveSidebarPlaylistOrder(containerId, endpoint);
            });

            sidebarContainer.addEventListener('dragend', () => {
                if (draggedItem) {
                    draggedItem.classList.remove('sidebar-dragging');
                }
                if (didDrag) {
                    saveSidebarPlaylistOrder(containerId, endpoint);
                }
                draggedItem = null;
                didDrag = false;
            });

            sidebarContainer.dataset.dragSortReady = 'true';
        }

        function loadStarredSidebarPlaylists() {
            const sidebarContainer = document.getElementById('sidebar-starred-playlists');
            const countDisplay = document.getElementById('sidebar-starred-count');
            if (!sidebarContainer) return;

            fetch('/api/get-favorited-playlists/')
                .then(r => r.json())
                .then(data => {
                    if (data.success && data.playlists) {
                        sidebarContainer.innerHTML = '';
                        if (countDisplay) countDisplay.textContent = data.playlists.length;

                        if (data.playlists.length === 0) {
                            // No favorited playlists - keep it clean
                            sidebarContainer.innerHTML = '';
                            return;
                        }

                        data.playlists.forEach(p => {
                            const link = document.createElement('a');
                            link.className = 'sidebar-pill flex-align';
                            link.style.textDecoration = 'none';
                            link.setAttribute('href', `/playlist/${p.id}/`);
                            link.setAttribute('data-playlist-id', p.id);

                            link.innerHTML = `<div style="width: 18px; height: 18px; border-radius: 3px; overflow: hidden; flex-shrink: 0; background: rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; position: relative;">
                                <img src="${p.cover}" style="width: 100%; height: 100%; object-fit: cover; display: block;" onerror="this.onerror=null; this.src='/media/playlists/default_playlist.png'">
                            </div><span>${p.name}</span>`;
                            sidebarContainer.appendChild(link);
                        });
                        initSidebarPlaylistDragSort('sidebar-starred-playlists', '/api/update-starred-playlist-order/');
                        syncSidebarWithURL(window.location.href);
                    }
                });
        }

        function toggleCollectPlaylist(btn, playlistId) {
            if (!window.AURORA.isAuthenticated) {
            if (typeof openAuthModal === 'function') {
                openAuthModal('login');
                showHubToast("Please login to collect playlists!");
            } else {
                showHubToast("Please login first!");
            }
            return;
            }

            const formData = new FormData();
            formData.append('playlist_id', playlistId);
            formData.append('csrfmiddlewaretoken', getCookie('csrftoken'));

            fetch('/api/toggle-playlist-favorite/', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    const svg = btn.querySelector('svg');
                    if (data.is_favorited) {
                        btn.classList.add('active');
                        svg.setAttribute('fill', '#FFD700');
                        svg.style.color = '#FFD700';
                        showHubToast("Added to starred playlists!");
                    } else {
                        btn.classList.remove('active');
                        svg.setAttribute('fill', 'currentColor');
                        svg.style.color = 'rgba(255,255,255,0.7)';
                        showHubToast("Removed from starred playlists.");
                    }
                    loadStarredSidebarPlaylists();
                } else {
                    showHubToast(data.error || "Action failed");
                }
            })
            .catch(err => {
                console.error(err);
                showHubToast("Connection error");
            });
        }

        function openCreatePlaylistModal() {
            var overlay = document.getElementById('create-playlist-overlay');
            var titleInput = document.getElementById('new-playlist-title');
            var privateCheckbox = document.getElementById('is-private-playlist');
            if (titleInput) titleInput.value = '';
            if (privateCheckbox) privateCheckbox.checked = false;
            if (overlay) { overlay.style.display = 'flex'; }
        }

        function toggleSidebarSection(btn, target_id) {
            var target_el = document.getElementById(target_id);
            if (target_el) {
                target_el.classList.toggle('collapsed');
                btn.classList.toggle('collapsed');
            }
        }

        // 3. Global Listeners for Modal Logic
        document.addEventListener('DOMContentLoaded', function () {
            // Initial Sidebar Load
            if (window.AURORA.isAuthenticated) {
            loadSidebarPlaylists();
            loadStarredSidebarPlaylists();
            }

            // Search Clear Logic
            const searchInput = document.getElementById('search-input');
            const clearBtn = document.getElementById('clear-search');

            if (searchInput && clearBtn) {
                const toggleClearBtn = () => {
                    clearBtn.style.display = searchInput.value ? 'flex' : 'none';
                };

                searchInput.addEventListener('input', toggleClearBtn);
                
                clearBtn.addEventListener('click', () => {
                    searchInput.value = '';
                    toggleClearBtn();
                    searchInput.focus();
                });

                // Initial check in case of page refresh/pre-filled value
                toggleClearBtn();

                // SPA Intercept for Search Form
                const searchForm = searchInput.closest('form');
                if (searchForm) {
                    searchForm.onsubmit = function(e) {
                        e.preventDefault();
                        const url = new URL(searchForm.action, window.location.origin);
                        const formData = new FormData(searchForm);
                        formData.forEach((value, key) => {
                            const trimmedValue = String(value).trim();
                            if (trimmedValue) {
                                url.searchParams.set(key, trimmedValue);
                            } else {
                                url.searchParams.delete(key);
                            }
                        });
                        const currentTab = new URL(window.location.href).searchParams.get('tab') || 'all_songs';
                        url.searchParams.set('tab', currentTab);
                        const activeTab = url.searchParams.get('tab');
                        if (activeTab === 'all_albums' || activeTab === 'all_artists') {
                            const grid = document.querySelector('.catalog-grid');
                            const measureTarget = grid || document.querySelector('.page-entrance');
                            if (measureTarget) {
                                const width = measureTarget.getBoundingClientRect().width;
                                const styles = grid ? window.getComputedStyle(grid) : null;
                                const gap = styles ? (parseFloat(styles.columnGap || styles.gap) || 25) : 25;
                                const minCardWidth = 180;
                                const columns = Math.max(1, Math.floor((width + gap) / (minCardWidth + gap)));
                                const pageSize = Math.max(8, Math.min(60, columns * 3));
                                url.searchParams.set('page_size', String(pageSize));
                            }
                        } else {
                            url.searchParams.delete('page_size');
                        }
                        url.searchParams.set('page', '1');
                        if (window.navigatePage) {
                            window.navigatePage(url.href);
                        } else {
                            window.location.href = url.pathname + url.search;
                        }
                    };
                }
            }

            // Handle Action Clicks (From Library list or Explore menus)
            document.addEventListener('click', function (e) {
                const addBtn = e.target.closest('.add-to-playlist-item');
                if (addBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    const songId = addBtn.getAttribute('data-song-id');
                    openPlaylistModal(songId);
                }
            });

            // Player "+" Button Connection
            const playerAddBtn = document.getElementById('player-add-btn');
            if (playerAddBtn) {
                playerAddBtn.onclick = (e) => {
                    e.preventDefault();
                    if (!window.currentSongId) {
                        showHubToast("No song is currently playing!");
                        return;
                    }
                    openPlaylistModal(window.currentSongId);
                };
            }

            // Modal Close Behaviors
            const closeModal = (id) => document.getElementById(id).style.display = 'none';

            const pmClose = document.getElementById('playlist-modal-close');
            if (pmClose) pmClose.onclick = () => closeModal('playlist-modal-overlay');

            const cpClose = document.getElementById('create-playlist-close');
            if (cpClose) cpClose.onclick = () => closeModal('create-playlist-overlay');

            const openCreateFromList = document.getElementById('open-create-from-list');
            if (openCreateFromList) {
                openCreateFromList.onclick = () => {
                    closeModal('playlist-modal-overlay');
                    openCreatePlaylistModal();
                };
            }

            const pOverlay = document.getElementById('playlist-modal-overlay');
            const cOverlay = document.getElementById('create-playlist-overlay');
            if (pOverlay) pOverlay.onmousedown = (e) => { if (e.target === pOverlay) closeModal('playlist-modal-overlay'); };
            if (cOverlay) cOverlay.onmousedown = (e) => { if (e.target === cOverlay) closeModal('create-playlist-overlay'); };

            const createForm = document.getElementById('create-playlist-form');
            if (createForm) {
                createForm.onsubmit = (e) => {
                    e.preventDefault();
                    createPlaylist();
                };
            }
            
            // Initialize back button status on load
            updateBackBtnStatus();

            // Initialize page features (Marquees, etc.)
            setTimeout(() => {
                if (window.initPageFeatures) window.initPageFeatures();
            }, 300); // Wait longer for layout to settle
        });

        // ======= HUB CROPPER ENGINE =======
        let cropperState = {
            img: null,
            originalFile: null,
            scale: 1,
            posX: 0,
            posY: 0,
            isDragging: false,
            startX: 0,
            startY: 0,
            callback: null,
            minRes: 320,
            isCircle: false
        };

        function openHubCropper(file, callback, isCircle = false) {
            cropperState.originalFile = file;
            cropperState.callback = callback;
            cropperState.isCircle = isCircle;
            
            const cropBox = document.querySelector('.crop-square');
            if (cropBox) {
                if (isCircle) cropBox.classList.add('is-circle');
                else cropBox.classList.remove('is-circle');
            }
            
            const reader = new FileReader();
            reader.onload = (e) => {
                const img = new Image();
                img.onload = () => {
                    const isValid = img.width >= cropperState.minRes && img.height >= cropperState.minRes;
                    const warning = document.getElementById('cropper-warning');
                    const saveBtn = document.getElementById('btn-crop-save');
                    const targetImg = document.getElementById('cropper-target-img');
                    
                    targetImg.src = img.src;
                    cropperState.img = img;
                    
                    if (!isValid) {
                        warning.innerText = `*Please use an image higher than ${cropperState.minRes}x${cropperState.minRes}`;
                        saveBtn.disabled = true;
                    } else {
                        warning.innerText = "";
                        saveBtn.disabled = false;
                    }

                    // Calculate scaling thresholds
                    const fitBoxScale = Math.max(320 / img.width, 320 / img.height);
                    const fitViewScale = Math.max(fitBoxScale, Math.min(440 / img.width, 380 / img.height));
                    
                    // We set the "Base Scale" as the smallest possible fill
                    cropperState.scale = fitBoxScale;
                    
                    // Default Zoom: Try to fit the container comfortably, but allow zooming in/out
                    // For a 1000px image, fitViewScale would be ~0.38-0.44, making the box look "accurate"
                    const defaultZoom = (fitViewScale / fitBoxScale) * 100;
                    
                    // Set slider bounds dynamically if needed, or just set current value
                    const slider = document.getElementById('cropper-zoom-slider');
                    slider.min = 100; // 100% of fitBoxScale
                    slider.max = Math.max(400, (2.0 / fitBoxScale) * 100); // Allow up to 2x native or at least 4x min
                    slider.value = defaultZoom;
                    
                    cropperState.posX = 0;
                    cropperState.posY = 0;
                    
                    applyCropperTransform();
                    
                    document.getElementById('hub-cropper-modal').classList.add('active');
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        }

        function closeHubCropper() {
            document.getElementById('hub-cropper-modal').classList.remove('active');
        }

        function applyCropperTransform() {
            const el = document.getElementById('cropper-target-img');
            const zoom = document.getElementById('cropper-zoom-slider').value / 100;
            const finalScale = cropperState.scale * zoom;
            el.style.transform = `translate(${cropperState.posX}px, ${cropperState.posY}px) scale(${finalScale})`;
        }

        const cropperBox = document.getElementById('cropper-view-box');
        if (cropperBox) {
            cropperBox.onmousedown = (e) => {
                cropperState.isDragging = true;
                cropperState.startX = e.clientX - cropperState.posX;
                cropperState.startY = e.clientY - cropperState.posY;
            };
            window.addEventListener('mousemove', (e) => {
                if (!cropperState.isDragging) return;
                cropperState.posX = e.clientX - cropperState.startX;
                cropperState.posY = e.clientY - cropperState.startY;
                applyCropperTransform();
            });
            window.addEventListener('mouseup', () => cropperState.isDragging = false);

            document.getElementById('cropper-zoom-slider').oninput = applyCropperTransform;
        }

        function handleCropSave() {
            const canvas = document.createElement('canvas');
            canvas.width = cropperState.minRes;
            canvas.height = cropperState.minRes;
            const ctx = canvas.getContext('2d');
            
            const zoom = document.getElementById('cropper-zoom-slider').value / 100;
            const finalScale = cropperState.scale * zoom;
            
            // ViewBox is 440x380. Center is (220, 190)
            const viewCenterX = 220;
            const viewCenterY = 190;
            
            const imgW = cropperState.img.width * finalScale;
            const imgH = cropperState.img.height * finalScale;
            
            const imgLeft = viewCenterX + cropperState.posX - (imgW / 2);
            const imgTop = viewCenterY + cropperState.posY - (imgH / 2);
            
            // Viewport is 320x320. Centered in ViewBox.
            const vLeft = 220 - 160; // 60
            const vTop = 190 - 160;  // 30
            
            const sx = (vLeft - imgLeft) / finalScale;
            const sy = (vTop - imgTop) / finalScale;
            const sSide = 320 / finalScale;
            
            ctx.drawImage(cropperState.img, sx, sy, sSide, sSide, 0, 0, canvas.width, canvas.height);
            
            canvas.toBlob((blob) => {
                const croppedFile = new File([blob], "cropped_cover.jpg", { type: "image/jpeg" });
                if (cropperState.callback) cropperState.callback(croppedFile);
                closeHubCropper();
            }, 'image/jpeg', 0.9);
        }

        // --- GLOBAL DIALOG SYSTEM ---
        window.showHubConfirm = function(title, message, onConfirm, onCancel = null) {
            const overlay = document.getElementById('hub-dialog-overlay');
            const titleEl = document.getElementById('hub-dialog-title');
            const msgEl = document.getElementById('hub-dialog-message');
            const confirmBtn = document.getElementById('hub-dialog-confirm');
            const cancelBtn = document.getElementById('hub-dialog-cancel');

            if (!overlay || !titleEl || !msgEl || !confirmBtn || !cancelBtn) return;

            titleEl.textContent = title;
            msgEl.textContent = message;
            cancelBtn.style.display = 'block';
            confirmBtn.textContent = 'Confirm';

            const closeDialog = () => {
                overlay.classList.remove('active');
                setTimeout(() => { overlay.style.display = 'none'; }, 300);
            };

            confirmBtn.onclick = () => {
                closeDialog();
                if (onConfirm) onConfirm();
            };

            cancelBtn.onclick = () => {
                closeDialog();
                if (onCancel) onCancel();
            };

            overlay.style.display = 'flex';
            setTimeout(() => { overlay.classList.add('active'); }, 10);
        };

        window.showHubAlert = function(title, message, onOk = null) {
            const overlay = document.getElementById('hub-dialog-overlay');
            const titleEl = document.getElementById('hub-dialog-title');
            const msgEl = document.getElementById('hub-dialog-message');
            const confirmBtn = document.getElementById('hub-dialog-confirm');
            const cancelBtn = document.getElementById('hub-dialog-cancel');

            if (!overlay || !titleEl || !msgEl || !confirmBtn || !cancelBtn) return;

            titleEl.textContent = title;
            msgEl.textContent = message;
            cancelBtn.style.display = 'none';
            confirmBtn.textContent = 'Got it';

            const closeDialog = () => {
                overlay.classList.remove('active');
                setTimeout(() => { overlay.style.display = 'none'; }, 300);
            };

            confirmBtn.onclick = () => {
                closeDialog();
                if (onOk) onOk();
            };

            overlay.style.display = 'flex';
            setTimeout(() => { overlay.classList.add('active'); }, 10);
        };
