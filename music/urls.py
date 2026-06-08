from django.urls import path
from . import views

app_name = 'music'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('discovery/', views.discovery_view, name='discovery'),
    # User Area - static library and song detail (initial static pages)
    path('library/', views.music_library_view, name='library'),
    # API endpoints
    path('api/playlists/', views.get_user_playlists, name='get_playlists'),
    path('api/add-to-playlist/', views.add_to_playlist, name='add_to_playlist'),
    path('api/create-playlist/', views.create_playlist, name='create_playlist'),
    path('api/update-sidebar-playlist-order/', views.update_sidebar_playlist_order, name='update_sidebar_playlist_order'),
    path('api/update-starred-playlist-order/', views.update_starred_playlist_order, name='update_starred_playlist_order'),
    path('api/increment-song-view/', views.increment_song_view, name='increment_song_view'),
    path('api/increment-playlist-view/', views.increment_playlist_view, name='increment_playlist_view'),
    path('api/playlist-details/<str:playlist_id>/', views.get_playlist_details, name='get_playlist_details'),
    path('api/record-recent-play/', views.record_recent_play, name='record_recent_play'),
    path('api/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('api/check-favorite/', views.check_favorite, name='check_favorite'),
    path('api/remove-from-playlist/', views.remove_from_playlist, name='remove_from_playlist'),
    path('api/toggle-playlist-favorite/', views.toggle_playlist_favorite, name='toggle_playlist_favorite'),
    path('api/get-favorited-playlists/', views.get_favorited_playlists, name='get_favorited_playlists'),
    path('api/song-details/<int:song_id>/', views.get_song_details, name='get_song_details'),
    path('playlist/<str:playlist_id>/', views.playlist_detail, name='playlist_detail_frontend'),
    path('playlist/<str:playlist_id>/edit/', views.playlist_detail, name='playlist_edit_frontend'),
    path('album/<path:album_name>/', views.album_detail, name='album_detail_frontend'),
    path('artist/<path:artist_name>/', views.artist_detail, name='artist_detail_frontend'),
    path('playing/', views.index, name='playing_frontend'),
    path('api/update-playlist/', views.update_playlist, name='update_playlist'),
    path('api/update-playlist-song-order/', views.update_playlist_song_order, name='update_playlist_song_order'),
    path('api/delete-playlist/', views.delete_playlist, name='delete_playlist'),
    path('api/delete-song/', views.delete_song, name='delete_song'),
    path('api/delete-user/', views.delete_user, name='delete_user'),
    path('api/download-playlist/<str:playlist_id>/', views.download_playlist_zip, name='download_playlist_zip'),
    path('api/download-songs/', views.download_songs_zip, name='download_songs_zip'),
    path('search/', views.music_library_view, name='search'),
    path('settings/', views.profile_settings, name='profile_settings'),
    path('comments/<int:song_id>/', views.song_comments_view, name='song_comments'),
    path('api/post-comment/', views.api_post_comment, name='api_post_comment'),
    path('api/toggle-comment-like/', views.api_toggle_comment_like, name='api_toggle_comment_like'),
    path('api/delete-comment/', views.api_delete_comment, name='api_delete_comment'),
    path('api/comments/<int:song_id>/', views.api_get_comments, name='api_get_comments'),
    path('api/recommend-fragment/', views.recommend_fragment_api, name='recommend_fragment_api'),
    path('api/type-songs/', views.type_songs_api, name='type_songs_api'),
]

