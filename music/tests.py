from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User as AuthUser
from django.utils import timezone
import datetime

from .models import User, Song, Playlist, Comment, PlayHistory, get_audio_duration


# ──────────────────────────────────────────────
# Model Tests
# ──────────────────────────────────────────────

class UserModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create(
            username='testuser',
            password='password123',
            status='Active',
            email='test@example.com',
        )

    def test_str_returns_username(self):
        """User __str__ should return the username."""
        self.assertEqual(str(self.user), 'testuser')


class SongModelTest(TestCase):

    def setUp(self):
        self.song = Song.objects.create(
            name='Test Song',
            song_type='Pop',
            release_date=datetime.date(2024, 1, 1),
        )

    def test_str_returns_song_name(self):
        """Song __str__ should return the song name."""
        self.assertEqual(str(self.song), 'Test Song')

    def test_default_views_is_zero(self):
        """Song views should default to 0."""
        self.assertEqual(self.song.views, 0)

    def test_default_album_is_unknown(self):
        """Song album should default to 'Unknown Album'."""
        self.assertEqual(self.song.album, 'Unknown Album')

    def test_created_at_is_set_on_create(self):
        """Song should keep a dedicated upload timestamp."""
        self.assertIsNotNone(self.song.created_at)

    def test_secondary_type_is_exclusive_on_save(self):
        """Secondary types should replace broader multi-type labels on save."""
        song = Song.objects.create(
            name='Secondary Song',
            song_type='Touhou | Game | Flan',
            release_date=datetime.date(2024, 1, 1),
        )

        self.assertEqual(song.song_type, 'Flan')

    def test_non_secondary_types_are_deduplicated_on_save(self):
        """Non-secondary multi-type labels should keep first-seen order."""
        song = Song.objects.create(
            name='Multi Type Song',
            song_type='Touhou | Game | Touhou',
            release_date=datetime.date(2024, 1, 1),
        )

        self.assertEqual(song.song_type, 'Touhou | Game')

    def test_annual_is_not_secondary_type(self):
        """Annual should remain a normal combinable type."""
        song = Song.objects.create(
            name='Annual Type Song',
            song_type='Touhou | Annual',
            release_date=datetime.date(2024, 1, 1),
        )

        self.assertEqual(song.song_type, 'Touhou | Annual')

    def test_miriya_is_secondary_type(self):
        """Miriya should be an exclusive secondary type."""
        song = Song.objects.create(
            name='Miriya Type Song',
            song_type='Touhou | Miriya',
            release_date=datetime.date(2024, 1, 1),
        )

        self.assertEqual(song.song_type, 'Miriya')

    def test_memories_is_secondary_type(self):
        """Memories should be an exclusive secondary type."""
        song = Song.objects.create(
            name='Memories Type Song',
            song_type='Touhou | Memories',
            release_date=datetime.date(2024, 1, 1),
        )

        self.assertEqual(song.song_type, 'Memories')

    def test_work_is_not_secondary_type(self):
        """Work should remain a normal combinable type."""
        song = Song.objects.create(
            name='Work Type Song',
            song_type='Touhou | Work',
            release_date=datetime.date(2024, 1, 1),
        )

        self.assertEqual(song.song_type, 'Touhou | Work')


class PlaylistModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create(
            username='playlistuser',
            password='password123',
            status='Active',
            email='playlist@example.com',
        )
        self.playlist = Playlist.objects.create(
            user=self.user,
            name='My Playlist',
        )

    def test_str_returns_playlist_name(self):
        """Playlist __str__ should return the playlist name."""
        self.assertEqual(str(self.playlist), 'My Playlist')

    def test_default_is_not_private(self):
        """Playlist should be public by default."""
        self.assertFalse(self.playlist.is_private)

    def test_default_views_is_zero(self):
        """Playlist views should default to 0."""
        self.assertEqual(self.playlist.views, 0)


class CommentModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create(
            username='commenter',
            password='password123',
            status='Active',
            email='comment@example.com',
        )
        self.song = Song.objects.create(
            name='Comment Song',
            song_type='Jazz',
            release_date=datetime.date(2024, 1, 1),
        )
        self.comment = Comment.objects.create(
            user=self.user,
            song=self.song,
            content='Great song!',
        )

    def test_str_format(self):
        """Comment __str__ should include username and song name."""
        result = str(self.comment)
        self.assertIn('commenter', result)
        self.assertIn('Comment Song', result)

    def test_default_good_count_is_zero(self):
        """Comment good_count should default to 0."""
        self.assertEqual(self.comment.good_count, 0)


class GetAudioDurationTest(TestCase):

    def test_invalid_path_returns_default(self):
        """get_audio_duration with invalid path should return '00:00'."""
        result = get_audio_duration('/nonexistent/path/file.mp3')
        self.assertEqual(result, '00:00')

    def test_empty_string_returns_default(self):
        """get_audio_duration with empty string should return '00:00'."""
        result = get_audio_duration('')
        self.assertEqual(result, '00:00')


# ──────────────────────────────────────────────
# View Tests
# ──────────────────────────────────────────────

class IndexViewTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_index_returns_200(self):
        """Home page should return HTTP 200."""
        response = self.client.get(reverse('music:index'))
        self.assertEqual(response.status_code, 200)

    def test_guest_index_hides_playlist_square(self):
        response = self.client.get(reverse('music:index'))

        self.assertNotContains(response, 'Playlist Square')
        self.assertNotContains(response, reverse('music:discovery'))
        self.assertContains(response, reverse('music:playlist_detail_frontend', args=['favorites']))
        self.assertContains(response, reverse('music:playlist_detail_frontend', args=['recent']))

    def test_guest_index_hides_see_all_and_type_load_more(self):
        for i in range(8):
            Song.objects.create(
                name=f'Guest Type Song {i}',
                album='Guest Type Album',
                arrangement='Guest Type Artist',
                song_type='Game',
                release_date=datetime.date(2024, 1, 1),
                download_link=f'songs/guest-type-{i}.mp3',
                views=i,
            )

        response = self.client.get(reverse('music:index'))

        self.assertNotContains(response, 'class="shelf-hdr-link"')
        self.assertNotContains(response, 'data-type="Game">Load More</button>')
        self.assertNotContains(response, '?sort=popular')
        self.assertNotContains(response, '?sort=-id')
        self.assertContains(response, 'var canLoadMoreTypes = !!(window.AURORA && window.AURORA.isAuthenticated);')

    def test_authenticated_index_shows_playlist_square(self):
        auth_user = AuthUser.objects.create_user(
            username='listener',
            email='listener@example.com',
            password='password123',
        )
        self.client.force_login(auth_user)

        response = self.client.get(reverse('music:index'))

        self.assertContains(response, 'Playlist Square')
        self.assertContains(response, reverse('music:discovery'))
        self.assertContains(response, '?sort=popular')
        self.assertContains(response, '?sort=-id')

    def test_guest_discovery_redirects_to_index(self):
        response = self.client.get(reverse('music:discovery'))

        self.assertRedirects(response, reverse('music:index'))

    def test_guest_player_social_buttons_are_auth_guarded(self):
        response = self.client.get(reverse('music:index'))

        self.assertContains(
            response,
            'if(window.AURORA && window.AURORA.isAuthenticated && window.currentSongId) toggleLike',
        )
        self.assertContains(
            response,
            'if(window.AURORA && window.AURORA.isAuthenticated && window.currentSongId)',
        )
        self.assertContains(response, 'player-menu-container auth-disabled')
        self.assertContains(response, 'disabled aria-disabled="true"')

    def test_player_scripts_keep_social_buttons_disabled_for_guests(self):
        with open('music/static/music/js/app.js', encoding='utf-8') as js_file:
            app_script = js_file.read()
        with open('music/static/music/js/player.js', encoding='utf-8') as js_file:
            player_script = js_file.read()

        self.assertIn('!window.AURORA || !window.AURORA.isAuthenticated', app_script)
        self.assertIn("likeContainerEl.classList.toggle('no-song', !isAuthenticated)", player_script)
        self.assertIn("commentBtnEl.classList.toggle('no-song', !isAuthenticated)", player_script)
        self.assertIn('window.togglePDVCommentMode = function(force) {', player_script)
        self.assertIn('if (!isAuthenticated) return;', player_script)
        self.assertIn("const btn = e.target.closest('.player-more-btn');", player_script)

    def test_guest_type_song_rows_do_not_render_artist_links(self):
        response = self.client.get(reverse('music:type_songs_api'), {
            'type': 'Game',
            'page': '1',
        })

        html = response.json()['html']
        self.assertNotIn('/artist/', html)
        self.assertNotIn('artist-link', html)

    def test_guest_playlist_empty_state_login_opens_auth_modal(self):
        response = self.client.get(reverse('music:playlist_detail_frontend', args=['recent']))

        self.assertContains(response, "window.openAuthModal")
        self.assertContains(response, "window.openAuthModal('login')")
        self.assertNotContains(response, "openLoginModal()")


class RegisterViewTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_register_page_returns_200(self):
        """Register page (GET) should return HTTP 200."""
        response = self.client.get(reverse('music:register'))
        self.assertEqual(response.status_code, 200)


class LibraryViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        Song.objects.create(
            name='Beta Song',
            album='Beta Album',
            arrangement='Beta Artist',
            song_type='Game',
            release_date=datetime.date(2024, 1, 1),
            download_link='songs/beta.mp3',
            views=5,
        )
        Song.objects.create(
            name='Beta Song 2',
            album='Beta Album',
            arrangement='Beta Artist',
            song_type='Game',
            release_date=datetime.date(2024, 1, 1),
            download_link='songs/beta-2.mp3',
            views=7,
        )
        Song.objects.create(
            name='Alpha Song',
            album='Alpha Album',
            arrangement='Alpha Artist',
            song_type='Game',
            release_date=datetime.date(2024, 1, 1),
            download_link='songs/alpha.mp3',
            views=10,
        )

    def test_library_returns_200(self):
        """Music library page should return HTTP 200."""
        response = self.client.get(reverse('music:library'))
        self.assertEqual(response.status_code, 200)

    def test_frontend_search_form_preserves_active_tab_like_admin(self):
        response = self.client.get(reverse('music:search'), {
            'q': 'beta',
            'tab': 'all_albums',
        })

        self.assertContains(response, 'name="tab" value="all_albums"')
        self.assertContains(response, 'value="beta"')

    def test_frontend_search_submit_uses_form_params_like_admin(self):
        with open('music/static/music/js/app.js', encoding='utf-8') as js_file:
            script = js_file.read()

        self.assertIn('const url = new URL(searchForm.action, window.location.origin);', script)
        self.assertIn('const formData = new FormData(searchForm);', script)
        self.assertIn("url.searchParams.set('page', '1');", script)
        self.assertNotIn("searchForm.action + '?q='", script)

    def test_guest_library_does_not_link_album_or_artist_names(self):
        response = self.client.get(reverse('music:library'), {'q': 'Beta'})

        self.assertContains(response, 'Beta Album')
        self.assertContains(response, 'Beta Artist')
        self.assertNotContains(response, '/album/Beta%20Album/')
        self.assertNotContains(response, '/artist/Beta%20Artist/')

    def test_authenticated_library_keeps_album_and_artist_links(self):
        auth_user = AuthUser.objects.create_user(
            username='listener',
            email='listener@example.com',
            password='password123',
        )
        self.client.force_login(auth_user)

        response = self.client.get(reverse('music:library'), {'q': 'Beta'})

        self.assertContains(response, '/album/Beta%20Album/')
        self.assertContains(response, '/artist/Beta%20Artist/')

    def test_sort_dropdown_only_shows_on_album_and_artist_tabs(self):
        response = self.client.get(reverse('music:library'), {'tab': 'all_songs'})
        self.assertNotContains(response, 'id="sort-dropdown"')
        self.assertContains(response, 'id="genre-dropdown"')

        response = self.client.get(reverse('music:library'), {'tab': 'all_albums'})
        self.assertContains(response, 'id="sort-dropdown"')
        self.assertNotContains(response, 'id="genre-dropdown"')
        self.assertEqual(response.context['current_sort'], 'name')

        response = self.client.get(reverse('music:library'), {'tab': 'all_artists'})
        self.assertContains(response, 'id="sort-dropdown"')
        self.assertNotContains(response, 'id="genre-dropdown"')
        self.assertEqual(response.context['current_sort'], 'name')

    def test_album_and_artist_tabs_default_to_name_sort(self):
        response = self.client.get(reverse('music:library'), {'tab': 'all_albums'})
        self.assertEqual([album['album'] for album in response.context['albums']], [
            'Alpha Album',
            'Beta Album',
        ])

        response = self.client.get(reverse('music:library'), {'tab': 'all_artists'})
        self.assertEqual([artist['arrangement'] for artist in response.context['artists']], [
            'Alpha Artist',
            'Beta Artist',
        ])

    def test_album_tab_can_sort_by_total_plays(self):
        response = self.client.get(reverse('music:library'), {
            'tab': 'all_albums',
            'sort': '-plays',
        })

        albums = list(response.context['albums'])
        self.assertEqual([album['album'] for album in albums], [
            'Beta Album',
            'Alpha Album',
        ])
        self.assertEqual(albums[0]['views'], 12)
        self.assertContains(response, 'Most Plays')

    def test_album_and_artist_tabs_are_paginated(self):
        for i in range(25):
            Song.objects.create(
                name=f'Catalog Song {i:02d}',
                album=f'Catalog Album {i:02d}',
                arrangement=f'Catalog Artist {i:02d}',
                song_type='Game',
                release_date=datetime.date(2024, 1, 1),
                download_link=f'songs/catalog-{i:02d}.mp3',
                views=i,
            )

        response = self.client.get(reverse('music:library'), {'tab': 'all_albums'})
        self.assertEqual(len(response.context['albums']), 12)
        self.assertTrue(response.context['page_obj'].has_next())

        response = self.client.get(reverse('music:library'), {'tab': 'all_artists'})
        self.assertEqual(len(response.context['artists']), 12)
        self.assertTrue(response.context['page_obj'].has_next())

        response = self.client.get(reverse('music:library'), {
            'tab': 'all_albums',
            'page_size': '12',
        })
        self.assertEqual(len(response.context['albums']), 12)
        self.assertEqual(response.context['catalog_page_size'], 12)

    def test_catalog_resize_keeps_current_page(self):
        with open('music/templates/music/library.html', encoding='utf-8') as template_file:
            template = template_file.read()

        resize_block = template.split('const bindCatalogPageSizeResize = () => {', 1)[1].split("setupDropdown('genre-dropdown'", 1)[0]
        self.assertIn("url.searchParams.set('page_size', String(pageSize));", resize_block)
        self.assertNotIn("url.searchParams.set('page', '1');", resize_block)


class PlaylistUpdateViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.auth_user = AuthUser.objects.create_user(
            username='playlist_editor',
            email='editor@example.com',
            password='password123',
        )
        self.custom_user = User.objects.create(
            username='playlist_editor',
            password='password123',
            status='Active',
            email='editor@example.com',
        )
        self.playlist = Playlist.objects.create(
            user=self.custom_user,
            name='Default Cover Playlist',
        )
        self.client.force_login(self.auth_user)

    def test_rename_without_cover_keeps_default_cover(self):
        response = self.client.post(reverse('music:update_playlist'), {
            'playlist_id': self.playlist.id,
            'name': 'Renamed Playlist',
            'introduction': self.playlist.introduction,
            'is_private': 'false',
        })

        self.assertEqual(response.status_code, 200)
        self.playlist.refresh_from_db()
        self.assertEqual(self.playlist.name, 'Renamed Playlist')
        self.assertEqual(self.playlist.cover.name, 'playlists/default_playlist.png')


class PlaylistCreateViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.auth_user = AuthUser.objects.create_user(
            username='playlist_creator',
            email='creator@example.com',
            password='password123',
        )
        self.custom_user = User.objects.create(
            username='playlist_creator',
            password='password123',
            status='Active',
            email='creator@example.com',
        )
        Playlist.objects.create(user=self.custom_user, name='First', position=1)
        Playlist.objects.create(user=self.custom_user, name='Second', position=2)
        self.client.force_login(self.auth_user)

    def test_new_playlist_is_created_at_front(self):
        response = self.client.post(reverse('music:create_playlist'), {
            'name': 'Newest',
            'is_private': 'false',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        names = list(Playlist.objects.filter(user=self.custom_user).order_by('position', 'id').values_list('name', flat=True))
        self.assertEqual(names, ['Newest', 'First', 'Second'])


class AdminDashboardViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin_user = AuthUser.objects.create_superuser(
            username='admin_dashboard',
            email='admin-dashboard@example.com',
            password='password123',
        )
        self.custom_user = User.objects.create(
            username='dashboard_listener',
            password='password123',
            status='Active',
            email='listener@example.com',
        )
        self.song = Song.objects.create(
            name='Dashboard Top Song',
            album='Dashboard Album',
            arrangement='Dashboard Artist',
            song_type='Electronic | Ambient',
            release_date=datetime.date.today(),
            download_link='songs/dashboard-top-song.mp3',
            views=42,
        )
        self.second_song = Song.objects.create(
            name='Dashboard Recent Song',
            album='Dashboard Album',
            arrangement='Dashboard Artist',
            song_type='Pop',
            release_date=datetime.date.today() - datetime.timedelta(days=30),
            download_link='songs/dashboard-recent-song.mp3',
            views=7,
        )
        now = timezone.now()
        Song.objects.filter(pk=self.song.pk).update(created_at=now - datetime.timedelta(days=1))
        Song.objects.filter(pk=self.second_song.pk).update(created_at=now - datetime.timedelta(days=9))
        Playlist.objects.create(user=self.custom_user, name='Dashboard Playlist')
        Comment.objects.create(user=self.custom_user, song=self.song, content='Useful dashboard data.')
        PlayHistory.objects.create(user=self.custom_user, song=self.song)
        self.client.force_login(self.admin_user)

    def test_admin_index_renders_analytics_dashboard(self):
        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin/dashboard.html')
        self.assertContains(response, 'Music catalog and user activity overview')
        self.assertContains(response, 'Recent Uploads')
        self.assertContains(response, 'Most Listened Songs')
        self.assertContains(response, 'Recently Active Users')
        self.assertContains(response, 'Song Type Mix')
        self.assertContains(response, 'Recent Activity')
        self.assertContains(response, 'Dashboard Top Song')
        self.assertContains(response, 'dashboard_listener')
        self.assertEqual(response.context['total_songs'], 2)
        self.assertEqual(response.context['total_plays'], 1)
        self.assertEqual(response.context['active_users'], 1)
        self.assertEqual(response.context['recent_upload_count'], 1)
        self.assertTrue(response.context['type_breakdown'])


class AdminLibrarySearchViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin_user = AuthUser.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123',
        )
        self.client.force_login(self.admin_user)
        self.song = Song.objects.create(
            name='Different Title',
            album='UNDERTALE Soundtrack',
            arrangement='Toby Fox',
            song_type='Game',
            release_date=datetime.date(2024, 1, 1),
            download_link='songs/different-title.mp3',
        )
        self.unknown_song = Song.objects.create(
            name='Needs Metadata',
            album='Unknown Album',
            arrangement='Unknown Artist',
            song_type='Game',
            release_date=datetime.date(2024, 1, 1),
            download_link='songs/needs-metadata.mp3',
        )

    def test_admin_search_keeps_tabs_visible_with_query(self):
        response = self.client.get(reverse('admin:music_song_changelist'), {
            'q': 'undertale',
            'tab': 'all_songs',
        })

        self.assertContains(response, 'Search Results for "undertale"')
        content = response.content.decode()
        self.assertIn('All Songs', content)
        self.assertIn('All Albums', content)
        self.assertIn('All Artists', content)
        self.assertIn('tab=all_songs', content)
        self.assertIn('tab=all_albums', content)
        self.assertIn('tab=all_artists', content)
        self.assertIn('q=undertale', content)
        self.assertIn('value="undertale"', content)

    def test_admin_search_album_tab_uses_album_results(self):
        response = self.client.get(reverse('admin:music_song_changelist'), {
            'q': 'undertale',
            'tab': 'all_albums',
        })

        self.assertEqual(response.context['active_tab'], 'all_albums')
        self.assertEqual(list(response.context['albums']), [{
            'album': 'UNDERTALE Soundtrack',
            'song_count': 1,
            'cover': 'covers/default_cover.jpg',
            'artist': 'Toby Fox',
            'views': 0,
        }])

    def test_admin_search_all_songs_matches_frontend_title_only(self):
        response = self.client.get(reverse('admin:music_song_changelist'), {
            'q': 'undertale',
            'tab': 'all_songs',
        })

        self.assertEqual(response.context['page_obj'].paginator.count, 0)

        Song.objects.create(
            name='Undertale Theme',
            album='Other Album',
            arrangement='Other Artist',
            song_type='Game',
            release_date=datetime.date(2024, 1, 2),
            download_link='songs/undertale-theme.mp3',
        )

        response = self.client.get(reverse('admin:music_song_changelist'), {
            'q': 'undertale',
            'tab': 'all_songs',
        })

        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertContains(response, 'Undertale Theme')

    def test_admin_unknown_search_album_tab_shows_unknown_album(self):
        response = self.client.get(reverse('admin:music_song_changelist'), {
            'q': 'unknown',
            'tab': 'all_albums',
        })

        albums = list(response.context['albums'])
        self.assertEqual(albums, [{
            'album': 'Unknown Album',
            'song_count': 1,
            'cover': 'covers/default_cover.jpg',
            'artist': 'Unknown Artist',
            'views': 0,
        }])

    def test_admin_unknown_search_artist_tab_shows_unknown_artist(self):
        response = self.client.get(reverse('admin:music_song_changelist'), {
            'q': 'unknown',
            'tab': 'all_artists',
        })

        self.assertEqual(list(response.context['artists']), [{
            'arrangement': 'Unknown Artist',
            'song_count': 1,
            'views': 0,
        }])

    def test_admin_library_tabs_include_unknown_metadata_without_search(self):
        response = self.client.get(reverse('admin:music_song_changelist'), {
            'tab': 'all_albums',
        })

        albums = list(response.context['albums'])
        self.assertTrue(any(album['album'] == 'Unknown Album' for album in albums))

        response = self.client.get(reverse('admin:music_song_changelist'), {
            'tab': 'all_artists',
        })
        self.assertTrue(any(artist['arrangement'] == 'Unknown Artist' for artist in response.context['artists']))

    def test_admin_highlighting_targets_metadata_links(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            template = template_file.read()

        self.assertIn("el.querySelectorAll('span, a')", template)
        self.assertIn("'.song-title-text'", template)
        self.assertIn("'.hover-marquee-content'", template)
        self.assertIn("'.catalog-card h5'", template)
        self.assertNotIn('text-shadow: none !important;', template)
        self.assertNotIn("has-search-highlight", template)

    def test_admin_metadata_marquee_matches_frontend_hover_behavior(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            change_list_template = template_file.read()
        with open('templates/admin/base_site.html', encoding='utf-8') as template_file:
            base_template = template_file.read()

        self.assertIn('.song-row .hover-marquee-wrapper.is-overflowing:hover .hover-marquee-content', change_list_template)
        self.assertIn('window.updateMarquees', change_list_template)
        self.assertIn('content.innerHTML = content.dataset.originalHtml', base_template)
        self.assertIn('js-marquee-unit js-marquee-spacer', base_template)
        self.assertIn('content.style.animationDuration = (sw / 60).toFixed(2)', base_template)

    def test_admin_search_hides_results_until_dom_enhancement_finishes(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            template = template_file.read()

        self.assertIn('{% if is_search_page %}admin-search-preinit{% endif %}', template)
        self.assertIn('.admin-search-preinit .song-list-body', template)
        self.assertIn("el.classList.remove('admin-search-preinit')", template)

    def test_admin_search_highlight_style_matches_frontend_except_color(self):
        with open('music/static/music/css/admin_player.css', encoding='utf-8') as css_file:
            css = css_file.read()

        highlight_css = css.split('.search-highlight {', 1)[1].split('}', 1)[0]
        self.assertIn('color: #FFD000 !important;', highlight_css)
        self.assertIn('font-weight: 700 !important;', highlight_css)
        self.assertIn('text-shadow: 0 0 12px rgba(255, 200, 0, 0.6);', highlight_css)
        self.assertNotIn('color: #00D2FF !important;', highlight_css)
        self.assertNotIn('font-weight: 900 !important;', highlight_css)

    def test_admin_song_rows_disable_blurred_hover_overlay(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            template = template_file.read()

        self.assertIn('.song-table-container .song-row:hover::before', template)
        self.assertIn('backdrop-filter: none !important;', template)

    def test_admin_sort_dropdown_only_shows_on_album_and_artist_tabs(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            template = template_file.read()

        self.assertIn('id="sort-dropdown"', template)
        self.assertIn("setupDropdown('sort-dropdown', 'sort')", template)
        self.assertIn('title="Sort by title"', template)
        self.assertIn('title="Sort by album"', template)
        self.assertIn('title="Sort by artist"', template)

        response = self.client.get(reverse('admin:music_song_changelist'), {'tab': 'all_songs'})
        self.assertNotContains(response, 'id="sort-dropdown"')
        self.assertContains(response, 'id="genre-dropdown"')

        response = self.client.get(reverse('admin:music_song_changelist'), {'tab': 'all_albums'})
        self.assertContains(response, 'id="sort-dropdown"')
        self.assertNotContains(response, 'id="genre-dropdown"')
        self.assertEqual(response.context['current_sort'], 'name')

        response = self.client.get(reverse('admin:music_song_changelist'), {'tab': 'all_artists'})
        self.assertContains(response, 'id="sort-dropdown"')
        self.assertNotContains(response, 'id="genre-dropdown"')
        self.assertEqual(response.context['current_sort'], 'name')

    def test_admin_header_hover_matches_frontend_without_restored_hover(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            template = template_file.read()

        self.assertIn('class="library-song-header"', template)
        self.assertNotIn('class="song-row song-header"', template)
        self.assertIn('.playlist-header-cell {', template)
        self.assertIn('overflow: hidden;', template)
        self.assertIn('text-overflow: ellipsis;', template)
        self.assertIn('white-space: nowrap;', template)
        self.assertIn('.playlist-header-cell.is-hoverable:hover {', template)
        hover_block = template.split('.playlist-header-cell.is-hoverable:hover {', 1)[1].split('}', 1)[0]
        self.assertIn('background: rgba(255, 45, 75, 0.12);', hover_block)
        self.assertNotIn('transform:', hover_block)
        self.assertNotIn('box-shadow:', hover_block)
        self.assertNotIn('is-restored-hover', template)
        self.assertNotIn('admin_library_sort_hover', template)
        self.assertNotIn('restoreAdminSortHover', template)

    def test_admin_genre_dropdown_hover_avoids_blur_layer_flicker(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            template = template_file.read()

        self.assertIn('#genre-dropdown .aurora-select-trigger', template)
        self.assertIn('backdrop-filter: none !important;', template)
        self.assertIn('#genre-dropdown .aurora-select-trigger:hover', template)
        self.assertIn('transform: none !important;', template)

    def test_admin_genre_dropdown_uses_internal_scrollbar(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            template = template_file.read()

        self.assertIn('#genre-dropdown .aurora-select-options', template)
        self.assertIn('max-height: min(360px, calc(100vh - 360px));', template)
        self.assertIn('overflow-y: auto;', template)
        self.assertIn('scrollbar-color: rgba(255, 45, 75, 0.72)', template)

    def test_admin_song_header_sort_supports_album_and_artist(self):
        response = self.client.get(reverse('admin:music_song_changelist'), {
            'tab': 'all_songs',
            'sort': 'album',
        })
        self.assertEqual(response.context['current_sort'], 'album')
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('admin:music_song_changelist'), {
            'tab': 'all_songs',
            'sort': 'artist',
        })
        self.assertEqual(response.context['current_sort'], 'artist')
        self.assertEqual(response.status_code, 200)

    def test_admin_album_and_artist_tabs_can_sort_by_total_plays(self):
        Song.objects.create(
            name='High Play Song',
            album='High Play Album',
            arrangement='High Play Artist',
            song_type='Game',
            release_date=datetime.date(2024, 1, 1),
            download_link='songs/high-play.mp3',
            views=25,
        )

        response = self.client.get(reverse('admin:music_song_changelist'), {
            'tab': 'all_albums',
            'sort': '-plays',
        })
        self.assertEqual(response.context['current_sort'], '-plays')
        self.assertEqual(list(response.context['albums'])[0]['album'], 'High Play Album')
        self.assertContains(response, 'Most Plays')

        response = self.client.get(reverse('admin:music_song_changelist'), {
            'tab': 'all_artists',
            'sort': '-plays',
        })
        self.assertEqual(response.context['current_sort'], '-plays')
        self.assertEqual(response.context['artists'][0]['arrangement'], 'High Play Artist')
        self.assertContains(response, 'Most Plays')

    def test_admin_album_and_artist_tabs_are_paginated(self):
        for i in range(25):
            Song.objects.create(
                name=f'Admin Catalog Song {i:02d}',
                album=f'Admin Catalog Album {i:02d}',
                arrangement=f'Admin Catalog Artist {i:02d}',
                song_type='Game',
                release_date=datetime.date(2024, 1, 1),
                download_link=f'songs/admin-catalog-{i:02d}.mp3',
                views=i,
            )

        response = self.client.get(reverse('admin:music_song_changelist'), {'tab': 'all_albums'})
        self.assertEqual(len(response.context['albums']), 12)
        self.assertTrue(response.context['page_obj'].has_next())

        response = self.client.get(reverse('admin:music_song_changelist'), {'tab': 'all_artists'})
        self.assertEqual(len(response.context['artists']), 12)
        self.assertTrue(response.context['page_obj'].has_next())

        response = self.client.get(reverse('admin:music_song_changelist'), {
            'tab': 'all_artists',
            'page_size': '12',
        })
        self.assertEqual(len(response.context['artists']), 12)
        self.assertEqual(response.context['catalog_page_size'], 12)

    def test_admin_catalog_resize_keeps_current_page(self):
        with open('templates/admin/music/song/change_list.html', encoding='utf-8') as template_file:
            template = template_file.read()

        resize_block = template.split('const bindCatalogPageSizeResize = () => {', 1)[1].split("setupDropdown('genre-dropdown'", 1)[0]
        self.assertIn("url.searchParams.set('page_size', String(pageSize));", resize_block)
        self.assertNotIn("url.searchParams.set('p', '0');", resize_block)
