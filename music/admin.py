from django.contrib import admin
from django.core.paginator import Paginator
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.db.models import Count, F, Max, Min, Q, Sum
from django.db import transaction
from datetime import datetime, timedelta
from django.db.models.functions import TruncDate
from django import forms
from django.utils import timezone
import os
import re
import tempfile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3
from .models import User, Song, Playlist, PlaylistSong, FavoriteSongPosition, Comment, PlayHistory, Feedback, Invitation
from .type_rules import TYPE_SEPARATOR, split_song_types


def _type_member_filter(type_name):
    """Match a Song whose pipe-separated song_type contains `type_name` as a member."""
    return (
        Q(song_type=type_name) |
        Q(song_type__startswith=f'{type_name}{TYPE_SEPARATOR}') |
        Q(song_type__endswith=f'{TYPE_SEPARATOR}{type_name}') |
        Q(song_type__icontains=f'{TYPE_SEPARATOR}{type_name}{TYPE_SEPARATOR}')
    )


class SongTypeListFilter(admin.SimpleListFilter):
    """Admin sidebar filter that lists each pipe-separated song_type member as its own option."""
    title = 'song type'
    parameter_name = 'song_type'

    def lookups(self, request, model_admin):
        seen = set()
        for raw in Song.objects.exclude(song_type__isnull=True).exclude(song_type='').values_list('song_type', flat=True):
            seen.update(split_song_types(raw))
        return sorted((t, t) for t in seen)

    def queryset(self, request, queryset):
        val = self.value()
        if not val:
            return queryset
        return queryset.filter(_type_member_filter(val))


class SongAdminForm(forms.ModelForm):
    class Meta:
        model = Song
        fields = '__all__'
        widgets = {
            'release_date': forms.DateInput(attrs={'type': 'date'}),
            'track_number': forms.NumberInput(attrs={'min': '1'}),
        }


class UserAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = '__all__'
        widgets = {
            'birth': forms.DateInput(attrs={'type': 'date'}),
        }


class CustomAdminSite(admin.AdminSite):
    site_header = "Aurora Admin Center"
    site_title = "Aurora Administration"
    index_title = "Welcome back, Administrator"
    login_template = 'admin/login.html'

    def _admin_changelist_url(self, app_label, model_name):
        return reverse(f'admin:{app_label}_{model_name}_changelist', current_app=self.name)

    def _format_admin_time(self, value):
        if not value:
            return ''
        return timezone.localtime(value).strftime('%m-%d %H:%M')

    def _type_breakdown(self, total_songs):
        counts = {}
        for raw_type in Song.objects.exclude(song_type__isnull=True).exclude(song_type='').values_list('song_type', flat=True):
            for type_name in split_song_types(raw_type):
                counts[type_name] = counts.get(type_name, 0) + 1

        return [
            {
                'name': type_name,
                'count': count,
                'percent': round((count / total_songs) * 100) if total_songs else 0,
            }
            for type_name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        ]

    def _recent_activity(self):
        rows = []

        for item in PlayHistory.objects.select_related('user', 'song').order_by('-played_at')[:8]:
            rows.append({
                'kind': 'Play',
                'title': item.song.name,
                'detail': f'{item.user.username} listened',
                'time': item.played_at,
                'time_label': self._format_admin_time(item.played_at),
            })

        for item in Comment.objects.select_related('user', 'song').order_by('-created_at')[:8]:
            rows.append({
                'kind': 'Comment',
                'title': item.song.name,
                'detail': f'{item.user.username} commented',
                'time': item.created_at,
                'time_label': self._format_admin_time(item.created_at),
            })

        for item in Playlist.objects.select_related('user').order_by('-created_at')[:8]:
            rows.append({
                'kind': 'Playlist',
                'title': item.name,
                'detail': f'{item.user.username} created playlist',
                'time': item.created_at,
                'time_label': self._format_admin_time(item.created_at),
            })

        fallback_time = timezone.now() - timedelta(days=36500)
        rows.sort(key=lambda row: row['time'] or fallback_time, reverse=True)
        return rows[:8]
    
    def index(self, request, extra_context=None):
        """Custom analytics dashboard index."""
        today = timezone.localdate()
        recent_cutoff = timezone.now() - timedelta(days=7)

        total_users = User.objects.count()
        total_songs = Song.objects.count()
        total_playlists = Playlist.objects.count()
        total_comments = Comment.objects.count()
        total_plays = PlayHistory.objects.count()
        active_users = PlayHistory.objects.values('user').distinct().count()
        total_feedbacks = Feedback.objects.count()
        recent_upload_count = Song.objects.filter(created_at__gte=recent_cutoff).count()
        recent_play_count = PlayHistory.objects.filter(played_at__gte=recent_cutoff).count()

        recent_songs = Song.objects.order_by('-created_at', '-id')[:6]
        top_songs = Song.objects.order_by('-views', 'name', 'id')[:6]
        active_user_rows = list(
            PlayHistory.objects.values('user__username', 'user__email')
            .annotate(play_count=Count('id'), last_seen=Max('played_at'))
            .order_by('-last_seen', '-play_count')[:6]
        )

        if not active_user_rows:
            active_user_rows = [
                {
                    'user__username': user.username,
                    'user__email': user.email,
                    'play_count': 0,
                    'last_seen': user.date_joined,
                }
                for user in User.objects.order_by('-id')[:6]
            ]

        catalog_trend = []
        max_catalog_count = 1
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            count = Song.objects.filter(created_at__date=date).count()
            max_catalog_count = max(max_catalog_count, count)
            catalog_trend.append({
                'label': date.strftime('%m-%d'),
                'count': count,
            })

        for row in catalog_trend:
            row['percent'] = round((row['count'] / max_catalog_count) * 100) if max_catalog_count else 0

        for row in active_user_rows:
            row['last_seen_label'] = self._format_admin_time(row.get('last_seen')) or 'No activity yet'

        song_changelist_url = self._admin_changelist_url('music', 'song')
        user_changelist_url = self._admin_changelist_url('music', 'user')

        extra_context = extra_context or {}
        extra_context.update({
            'total_users': total_users,
            'total_songs': total_songs,
            'total_playlists': total_playlists,
            'total_comments': total_comments,
            'total_plays': total_plays,
            'active_users': active_users,
            'total_feedbacks': total_feedbacks,
            'recent_upload_count': recent_upload_count,
            'recent_play_count': recent_play_count,
            'recent_songs': recent_songs,
            'top_songs': top_songs,
            'active_user_rows': active_user_rows,
            'type_breakdown': self._type_breakdown(total_songs),
            'catalog_trend': catalog_trend,
            'recent_activity': self._recent_activity(),
            'dashboard_updated_at': self._format_admin_time(timezone.now()),
            'song_changelist_url': song_changelist_url,
            'user_changelist_url': user_changelist_url,
            'playlist_changelist_url': self._admin_changelist_url('music', 'playlist'),
            'comment_changelist_url': self._admin_changelist_url('music', 'comment'),
        })
        
        request.current_app = self.name
        return TemplateResponse(request, 'admin/dashboard.html', extra_context)
    
    def get_urls(self):
        """Add custom URLs"""
        urls = super().get_urls()
        return urls


# Create instance of custom AdminSite
admin_site = CustomAdminSite(name='admin')

from django.utils.html import format_html

class ReturnToListAdminMixin:
    def _changelist_url(self):
        opts = self.model._meta
        return reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist', current_app=self.admin_site.name)

    def _get_return_url(self, request):
        url = request.POST.get('next') or request.GET.get('next')
        if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
            return url
        return self._changelist_url()

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['return_url'] = self._get_return_url(request)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def _replace_redirect_response(self, request, url):
        return TemplateResponse(request, 'admin/replace_redirect.html', {'target_url': url})

    def response_change(self, request, obj):
        if '_save' in request.POST:
            return self._replace_redirect_response(request, self._get_return_url(request))
        return super().response_change(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        if '_save' in request.POST:
            return self._replace_redirect_response(request, self._get_return_url(request))
        return super().response_add(request, obj, post_url_continue)


class SongAdmin(ReturnToListAdminMixin, admin.ModelAdmin):
    form = SongAdminForm
    list_display = ('name', 'album', 'track_number', 'cover_preview', 'song_type', 'release_date')
    search_fields = ('name', 'album')
    list_filter = (SongTypeListFilter, 'release_date')
    change_list_template = 'admin/music/song/change_list.html'
    change_form_template = 'admin/music/song/change_form.html'

    def _get_zero_based_page(self, request):
        if request.GET.get('p') is None and request.GET.get('page') is not None:
            try:
                return int(request.GET.get('page'))
            except (TypeError, ValueError):
                return 1
        try:
            return int(request.GET.get('p', 0)) + 1
        except (TypeError, ValueError):
            return 1

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                'album/<path:album_name>/',
                self.admin_site.admin_view(self.album_detail_view),
                name=f'{opts.app_label}_{opts.model_name}_album_detail',
            ),
            path(
                'artist/<path:artist_name>/',
                self.admin_site.admin_view(self.artist_detail_view),
                name=f'{opts.app_label}_{opts.model_name}_artist_detail',
            ),
            path(
                'update-track-order/',
                self.admin_site.admin_view(self.update_track_order_view),
                name=f'{opts.app_label}_{opts.model_name}_update_track_order',
            ),
            path(
                'parse-upload-metadata/',
                self.admin_site.admin_view(self.parse_upload_metadata_view),
                name=f'{opts.app_label}_{opts.model_name}_parse_upload_metadata',
            ),
        ]
        return custom_urls + urls

    def _clean_artist(self, raw):
        if not raw:
            return ''
        return re.sub(r'\s*/\s*', ' | ', raw.strip())

    def _fix_mojibake_text(self, raw):
        if not raw:
            return raw
        try:
            fixed = raw.encode('latin1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return raw
        return fixed or raw

    def _parse_track_number(self, raw):
        if not raw:
            return ''
        match = re.search(r'\d+', str(raw))
        return match.group(0) if match else ''

    def _parse_id3_date(self, tags):
        for frame_name in ('TDRL', 'TDRC', 'TDOR', 'TYER'):
            frames = tags.getall(frame_name)
            if not frames:
                continue
            raw = str(frames[0].text[0] if getattr(frames[0], 'text', None) else frames[0]).strip()
            match = re.search(r'(\d{4})(?:[-/.](\d{1,2}))?(?:[-/.](\d{1,2}))?', raw)
            if not match:
                continue
            year = int(match.group(1))
            month = int(match.group(2) or 1)
            day = int(match.group(3) or 1)
            try:
                return datetime(year, month, day).date().isoformat()
            except ValueError:
                return ''
        return ''

    def parse_upload_metadata_view(self, request):
        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'POST only'}, status=405)

        upload = request.FILES.get('audio')
        if not upload:
            return JsonResponse({'success': False, 'error': 'Missing audio file'}, status=400)

        suffix = os.path.splitext(upload.name)[1] or '.mp3'
        temp_path = ''
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_path = tmp.name
                for chunk in upload.chunks():
                    tmp.write(chunk)

            try:
                easy = EasyID3(temp_path)
            except Exception:
                easy = {}

            title = (self._fix_mojibake_text(easy.get('title', [None])[0]) or os.path.splitext(upload.name)[0]).strip()
            artist = self._clean_artist(self._fix_mojibake_text(easy.get('artist', [None])[0]) or '')
            album = (self._fix_mojibake_text(easy.get('album', [None])[0]) or '').strip()
            track_number = self._parse_track_number(easy.get('tracknumber', [None])[0])

            release_date = ''
            try:
                release_date = self._parse_id3_date(ID3(temp_path))
            except Exception:
                release_date = ''

            return JsonResponse({
                'success': True,
                'metadata': {
                    'name': title,
                    'arrangement': artist,
                    'album': album,
                    'track_number': track_number,
                    'release_date': release_date,
                }
            })
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _song_payload(self, song):
        return {
            'id': song.id,
            'title': song.name,
            'artist': song.arrangement,
            'album': song.album,
            'cover': song.cover.url if song.cover else '/media/covers/default_cover.jpg',
            'file_url': song.download_link.url if song.download_link else '',
            'song_type': song.song_type or '',
            'track_number': song.track_number,
            'views': song.views or 0,
        }

    def _artist_filter(self, artist_name):
        return (
            Q(arrangement=artist_name) |
            Q(arrangement__startswith=f'{artist_name} | ') |
            Q(arrangement__endswith=f' | {artist_name}') |
            Q(arrangement__icontains=f' | {artist_name} | ')
        )

    def update_track_order_view(self, request):
        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'POST only'}, status=405)

        raw_ids = request.POST.get('song_ids', '')
        scope_type = request.POST.get('scope_type', '')
        scope_name = request.POST.get('scope_name', '')

        try:
            song_ids = [int(sid) for sid in raw_ids.split(',') if sid.strip()]
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid song ids'}, status=400)

        try:
            position_offset = max(int(request.POST.get('position_offset', 0)), 0)
        except (TypeError, ValueError):
            position_offset = 0

        if not song_ids:
            return JsonResponse({'success': False, 'error': 'Missing song ids'}, status=400)

        if len(song_ids) != len(set(song_ids)):
            return JsonResponse({'success': False, 'error': 'Duplicate song ids'}, status=400)

        songs_qs = Song.objects.filter(id__in=song_ids)
        if scope_type == 'album':
            songs_qs = songs_qs.filter(album=scope_name)
        elif scope_type == 'artist':
            songs_qs = songs_qs.filter(self._artist_filter(scope_name))
        else:
            return JsonResponse({'success': False, 'error': 'Invalid scope'}, status=400)

        songs_by_id = {song.id: song for song in songs_qs}
        if len(songs_by_id) != len(song_ids):
            return JsonResponse({'success': False, 'error': 'Song scope mismatch'}, status=400)

        with transaction.atomic():
            for position, song_id in enumerate(song_ids, start=position_offset + 1):
                songs_by_id[song_id].track_number = position
            Song.objects.bulk_update(list(songs_by_id.values()), ['track_number'])

        return JsonResponse({'success': True})

    def album_detail_view(self, request, album_name):
        current_sort = request.GET.get('sort') or 'default'
        if current_sort not in ['default', 'title_asc', 'title_desc', 'artist_asc', 'artist_desc']:
            current_sort = 'default'
        songs = Song.objects.filter(album=album_name)
        if current_sort == 'title_asc':
            songs = songs.order_by('name', 'id')
        elif current_sort == 'title_desc':
            songs = songs.order_by('-name', '-id')
        elif current_sort == 'artist_asc':
            songs = songs.order_by('arrangement', 'id')
        elif current_sort == 'artist_desc':
            songs = songs.order_by('-arrangement', '-id')
        else:
            songs = songs.order_by(F('track_number').asc(nulls_last=True), 'name', 'id')

        total_songs = songs.count()
        limit = 50
        try:
            offset = max(int(request.GET.get('offset', 0)), 0)
        except (TypeError, ValueError):
            offset = 0

        if request.GET.get('partial') == 'songs':
            page_songs = list(songs[offset:offset + limit])
            return JsonResponse({
                'songs': [self._song_payload(song) for song in page_songs],
                'offset': offset,
                'next_offset': offset + len(page_songs),
                'has_more': offset + len(page_songs) < total_songs,
                'total': total_songs,
            })

        visible_songs = list(songs[:limit])
        representative_song = songs.first()
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'current_sort': current_sort,
            'album': {
                'name': album_name,
                'cover': representative_song.cover.url if representative_song and representative_song.cover else '/media/covers/default_cover.jpg',
                'artist': representative_song.arrangement if representative_song else '',
                'song_count': total_songs,
                'songs': [self._song_payload(song) for song in visible_songs],
            },
            'changelist_url': self._changelist_url(),
            'initial_song_count': len(visible_songs),
            'has_more_songs': len(visible_songs) < total_songs,
            'album_song_page_size': limit,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(request, 'admin/music/song/album_detail.html', context)

    def artist_detail_view(self, request, artist_name):
        current_sort = request.GET.get('sort') or 'default'
        if current_sort not in ['default', 'title_asc', 'title_desc', 'album_asc', 'album_desc']:
            current_sort = 'default'

        active_tab = request.GET.get('tab', 'songs')
        if active_tab not in ['songs', 'albums']:
            active_tab = 'songs'

        songs = Song.objects.filter(self._artist_filter(artist_name))
        if current_sort == 'title_asc':
            songs = songs.order_by('name', 'id')
        elif current_sort == 'title_desc':
            songs = songs.order_by('-name', '-id')
        elif current_sort == 'album_asc':
            songs = songs.order_by('album', 'name', 'id')
        elif current_sort == 'album_desc':
            songs = songs.order_by('-album', 'name', '-id')
        else:
            songs = songs.order_by('album', F('track_number').asc(nulls_last=True), 'name', 'id')

        album_rows = list(songs.values('album').order_by('album').annotate(
            song_count=Count('id'),
            cover=Min('cover'),
        ).exclude(Q(album__isnull=True) | Q(album='') | Q(album__iexact='Unknown Album')))
        album_names = [row['album'] for row in album_rows]
        album_total_counts = {
            row['album']: row['total_song_count']
            for row in Song.objects.filter(album__in=album_names).values('album').annotate(
                total_song_count=Count('id')
            )
        }

        albums = [
            {
                'name': row['album'],
                'song_count': row['song_count'],
                'total_song_count': album_total_counts.get(row['album'], row['song_count']),
                'cover': settings.MEDIA_URL + (row['cover'] or 'covers/default_cover.jpg'),
            }
            for row in album_rows
        ]

        total_song_count = songs.count()
        limit = 50
        try:
            offset = max(int(request.GET.get('offset', 0)), 0)
        except (TypeError, ValueError):
            offset = 0

        if request.GET.get('partial') == 'songs':
            page_songs = list(songs[offset:offset + limit])
            return JsonResponse({
                'songs': [self._song_payload(song) for song in page_songs],
                'offset': offset,
                'next_offset': offset + len(page_songs),
                'has_more': offset + len(page_songs) < total_song_count,
                'total': total_song_count,
            })

        visible_songs = list(songs[:limit])

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'active_tab': active_tab,
            'current_sort': current_sort,
            'artist': {
                'name': artist_name,
                'song_count': total_song_count,
                'album_count': len(albums),
                'views': songs.aggregate(total=Sum('views'))['total'] or 0,
                'songs': [self._song_payload(song) for song in visible_songs],
                'albums': albums,
            },
            'changelist_url': self._changelist_url(),
            'initial_song_count': len(visible_songs),
            'has_more_songs': len(visible_songs) < total_song_count,
            'artist_song_page_size': limit,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(request, 'admin/music/song/artist_detail.html', context)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            try:
                obj = self.get_queryset(request).get(pk=object_id)
                if obj.cover:
                    extra_context['cover_cache_buster'] = int(os.path.getmtime(obj.cover.path))
            except Exception:
                pass
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        lyrics_marker = request.POST.get('lyrics_marker')
        if lyrics_marker in {'puremusic', 'needlyrics'}:
            obj.lyrics = lyrics_marker
        super().save_model(request, obj, form, change)

    def changelist_view(self, request, extra_context=None):
        from .models import Song

        # This changelist is fully custom. Keep admin's native ChangeList away from
        # our UI params such as sort/genre/tab, otherwise it redirects to e=1.
        params = request.GET.copy()
        tab = params.get('tab', 'all_songs')
        requested_sort = params.get('sort')
        sort_session_key = 'admin_library_sort'
        song_valid_sorts = {'id', '-id', 'name', '-name', 'album', '-album', 'artist', '-artist', 'date', 'views', '-views', 'popular'}
        catalog_valid_sorts = {'name', '-name', 'song_count', '-song_count', 'plays', '-plays'}
        if tab == 'all_songs':
            sort = requested_sort or request.session.get(sort_session_key, 'id')
            if sort not in song_valid_sorts:
                sort = 'id'
        else:
            sort = requested_sort or 'name'
            if sort not in catalog_valid_sorts:
                sort = 'name'
        if requested_sort is not None and tab == 'all_songs':
            request.session[sort_session_key] = sort
        genre = params.get('genre', '')
        q = request.GET.get('q', '')
        try:
            catalog_page_size = int(params.get('page_size', 12))
        except (TypeError, ValueError):
            catalog_page_size = 12
        catalog_page_size = max(8, min(60, catalog_page_size))
        
        extra_context = extra_context or {}
        extra_context.update({
            'q': q,
            'active_tab': tab,
            'current_sort': sort,
            'current_genre': genre,
            'catalog_page_size': catalog_page_size,
            'is_search_page': bool(q),
        })

        # 2. Songs (Page Obj) - Use cl logic later or manual here
        # We'll let super().changelist_view provide the 'cl' for songs
        # But we need page_obj for the library.html template logic
        songs = Song.objects.all()
        if q:
            songs = songs.filter(name__icontains=q)
        if genre:
            songs = songs.filter(_type_member_filter(genre))
        
        sort_map = {
            'name': 'name',
            '-name': '-name',
            'album': 'album',
            '-album': '-album',
            'artist': 'arrangement',
            '-artist': '-arrangement',
            'date': '-release_date',
            'views': 'views',
            '-views': '-views',
            'popular': '-views',
            'id': 'id',
            '-id': '-id',
        }
        songs = songs.order_by(sort_map.get(sort, 'id'))
        
        paginator = Paginator(songs, 20)
        page_num = request.GET.get('p', 0)
        try:
            page_num = int(page_num) + 1
        except:
            page_num = 1
        extra_context['page_obj'] = paginator.get_page(page_num)

        # 3. Albums & Artists
        albums_qs = Song.objects.values('album').annotate(
            song_count=Count('id'),
            cover=Min('cover'),
            artist=Max('arrangement'),
            views=Sum('views'),
        ).exclude(Q(album__isnull=True) | Q(album=''))
        if q: albums_qs = albums_qs.filter(album__icontains=q)
        album_sort_map = {
            'name': 'album',
            '-name': '-album',
            'song_count': 'song_count',
            '-song_count': '-song_count',
            'plays': 'views',
            '-plays': '-views',
        }
        albums_qs = albums_qs.order_by(album_sort_map.get(sort, 'album'), 'album')
        if tab == 'all_albums':
            paginator = Paginator(albums_qs, catalog_page_size)
            extra_context['page_obj'] = paginator.get_page(page_num)
            extra_context['albums'] = extra_context['page_obj']
        else:
            extra_context['albums'] = albums_qs

        raw_artists = Song.objects.exclude(Q(arrangement__isnull=True) | Q(arrangement=''))
        raw_artists = raw_artists.values('arrangement', 'views')
        artist_map = {}
        for s in raw_artists:
            names = [n.strip() for n in str(s['arrangement']).split('|') if n.strip()]
            for name in names:
                if q and q.lower() not in name.lower(): continue
                if name not in artist_map:
                    artist_map[name] = {'arrangement': name, 'song_count': 0, 'views': 0}
                artist_map[name]['song_count'] += 1
                artist_map[name]['views'] += (s['views'] or 0)
        if sort == '-name':
            artists = sorted(artist_map.values(), key=lambda x: str(x['arrangement']).casefold(), reverse=True)
        elif sort == 'song_count':
            artists = sorted(artist_map.values(), key=lambda x: (x['song_count'], str(x['arrangement']).casefold()))
        elif sort == '-song_count':
            artists = sorted(artist_map.values(), key=lambda x: (-x['song_count'], str(x['arrangement']).casefold()))
        elif sort == 'plays':
            artists = sorted(artist_map.values(), key=lambda x: (x['views'], str(x['arrangement']).casefold()))
        elif sort == '-plays':
            artists = sorted(artist_map.values(), key=lambda x: (-x['views'], str(x['arrangement']).casefold()))
        else:
            artists = sorted(artist_map.values(), key=lambda x: str(x['arrangement']).casefold())
        if tab == 'all_artists':
            paginator = Paginator(artists, catalog_page_size)
            extra_context['page_obj'] = paginator.get_page(page_num)
            extra_context['artists'] = extra_context['page_obj']
        else:
            extra_context['artists'] = artists

        # 4. Genres (pipe-separated, one option per member)
        genres_raw = Song.objects.values_list('song_type', flat=True).distinct()
        genres_set = set()
        for g_str in genres_raw:
            if g_str:
                for p in [p.strip() for p in str(g_str).split('|')]:
                    if p: genres_set.add(p)
        extra_context['genres'] = sorted(list(genres_set))
        extra_context['liked_song_ids'] = []

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'module_name': str(self.model._meta.verbose_name_plural),
            'has_view_permission': self.has_view_permission(request),
            'has_add_permission': self.has_add_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'has_delete_permission': self.has_delete_permission(request),
            **extra_context,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(request, self.change_list_template, context)

    def cover_preview(self, obj):
        if obj.cover:
            try:
                version = int(os.path.getmtime(obj.cover.path))
                return format_html('<img src="{}?v={}" width="50" height="50" style="object-fit:cover; border-radius:4px;" />', obj.cover.url, version)
            except ValueError:
                return "No File"
            except OSError:
                return format_html('<img src="{}" width="50" height="50" style="object-fit:cover; border-radius:4px;" />', obj.cover.url)
        return "No Image"
    cover_preview.short_description = 'Cover'

class UserAdmin(ReturnToListAdminMixin, admin.ModelAdmin):
    form = UserAdminForm
    list_display = ('username', 'email', 'avatar_preview', 'status_tag')
    search_fields = ('username', 'email')
    list_filter = ('status',)
    actions = ['ban_users', 'unban_users']
    change_list_template = 'admin/music/user/change_list.html'
    change_form_template = 'admin/music/user/change_form.html'

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            try:
                obj = self.get_queryset(request).get(pk=object_id)
                if obj.avatar:
                    extra_context['avatar_cache_buster'] = int(os.path.getmtime(obj.avatar.path))
            except Exception:
                pass
        return super().changeform_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        from django.core.paginator import Paginator
        from django.db.models import Q

        request.GET = request.GET.copy()
        q = request.GET.get('q', '')

        users = User.objects.exclude(username=request.user.username).order_by('-date_joined')
        if q:
            users = users.filter(Q(username__icontains=q) | Q(email__icontains=q))

        paginator = Paginator(users, 20)
        page_num = request.GET.get('p', 0)
        try:
            page_num = int(page_num) + 1
        except:
            page_num = 1

        extra_context = extra_context or {}
        extra_context['page_obj'] = paginator.get_page(page_num)
        extra_context['q'] = q

        return super().changelist_view(request, extra_context=extra_context)

    def avatar_preview(self, obj):
        if obj.avatar:
            try:
                version = int(os.path.getmtime(obj.avatar.path))
                return format_html('<img src="{}?v={}" width="40" height="40" style="object-fit:cover; border-radius:50%;" />', obj.avatar.url, version)
            except ValueError:
                return "No File"
            except OSError:
                return format_html('<img src="{}" width="40" height="40" style="object-fit:cover; border-radius:50%;" />', obj.avatar.url)
        return "No Image"
    avatar_preview.short_description = 'Avatar'

    def status_tag(self, obj):
        color = 'green' if obj.status.lower() in ['active', 'normal'] else 'red'
        return format_html('<span style="color: {}; font-weight:bold;">{}</span>', color, obj.status)
    status_tag.short_description = 'Status'

    @admin.action(description='Ban selected users')
    def ban_users(self, request, queryset):
        updated = queryset.update(status='Banned')
        self.message_user(request, f'Successfully banned {updated} users.')

    @admin.action(description='Unban selected users')
    def unban_users(self, request, queryset):
        updated = queryset.update(status='Active')
        self.message_user(request, f'Successfully unbanned {updated} users.')

# Register models to custom admin site
admin_site.register(User, UserAdmin)
admin_site.register(Song, SongAdmin)
admin_site.register(Playlist)
admin_site.register(PlaylistSong)
admin_site.register(FavoriteSongPosition)
admin_site.register(Comment)
admin_site.register(PlayHistory)
admin_site.register(Feedback)
admin_site.register(Invitation)
