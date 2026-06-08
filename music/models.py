from django.db import models
from django.contrib.auth.models import User as AuthUser
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.conf import settings
import os
import re
from mutagen.mp3 import MP3
from .type_rules import normalize_song_type

def get_audio_duration(file_path):
    try:
        audio = MP3(file_path)
        length = int(audio.info.length)
        minutes = length // 60
        seconds = length % 60
        return f"{minutes:02d}:{seconds:02d}"
    except Exception as e:
        return "00:00"

def delete_file_on_disk(file_field):
    """Helper to delete a file from the filesystem."""
    if file_field and hasattr(file_field, 'path'):
        try:
            # Check existence immediately before trying to delete
            if os.path.exists(file_field.path):
                os.remove(file_field.path)
        except Exception as e:
            print(f"[Models] Error deleting file {file_field.name}: {e}")

def song_cover_path(instance, filename):
    ext = filename.split('.')[-1]
    safe_name = re.sub(r'[^\w\s-]', '', instance.name).strip().replace(' ', '_')
    prefix = f"{instance.id}_" if instance.id else ""
    return os.path.join('covers', f"{prefix}{safe_name}.{ext}")

def playlist_cover_path(instance, filename):
    ext = filename.split('.')[-1]
    safe_name = re.sub(r'[^\w\s-]', '', instance.name).strip().replace(' ', '_')
    prefix = f"{instance.id}_" if instance.id else ""
    return os.path.join('playlists', f"{prefix}{safe_name}.{ext}")

def song_audio_path(instance, filename):
    ext = filename.split('.')[-1]
    safe_name = re.sub(r'[^\w\s-]', '', instance.name).strip().replace(' ', '_')
    prefix = f"{instance.id}_" if instance.id else ""
    return os.path.join('songs', f"{prefix}{safe_name}.{ext}")

def song_lrc_path(instance, filename):
    ext = filename.split('.')[-1]
    safe_name = re.sub(r'[^\w\s-]', '', instance.name).strip().replace(' ', '_')
    prefix = f"{instance.id}_" if instance.id else ""
    return os.path.join('lyrics', f"{prefix}{safe_name}.{ext}")

# 1. User Model
class User(models.Model):
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    avatar = models.ImageField(upload_to='avatars/', default='avatars/default.jpeg')
    date_joined = models.DateTimeField(auto_now_add=True, null=True)
    birth = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=100)
    email = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=11, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.username


# 2. Song Model
class Song(models.Model):
    name = models.CharField(max_length=100) 
    album = models.CharField(max_length=100, default='Unknown Album', null=True, blank=True)
    track_number = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    lyrics = models.FileField(upload_to=song_lrc_path, null=True, blank=True, default='puremusic')
    cover = models.ImageField(upload_to=song_cover_path, default='covers/default_cover.jpg')
    arrangement = models.CharField(max_length=100, default='Unknown Artist', null=True, blank=True)
    song_type = models.CharField(max_length=100)
    introduction = models.TextField(default='No Introduction')
    release_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True, null=True, db_index=True)
    views = models.IntegerField(default=0)
    download_link = models.FileField(upload_to=song_audio_path, null=True, blank=True)
    
    favorited_by = models.ManyToManyField(User, related_name='favorite_songs', blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


# 3. Playlist Model
class Playlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='playlists')
    name = models.CharField(max_length=100)
    cover = models.ImageField(upload_to=playlist_cover_path, default='playlists/default_playlist.png')
    is_private = models.BooleanField(default=False)
    views = models.IntegerField(default=0)
    introduction = models.TextField(default='No Description', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    position = models.PositiveIntegerField(default=0, db_index=True)
    songs = models.ManyToManyField(Song, related_name='included_in_playlists', blank=True)
    favorited_by = models.ManyToManyField(User, related_name='favorited_playlists', blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['position', 'id']


class PlaylistSong(models.Model):
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='song_positions')
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='playlist_positions')
    position = models.PositiveIntegerField(default=0, db_index=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']
        unique_together = ('playlist', 'song')
        indexes = [
            models.Index(fields=['playlist', 'position']),
        ]

    def __str__(self):
        return f"{self.playlist.name} - {self.position}: {self.song.name}"


class FavoritePlaylistPosition(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorite_playlist_positions')
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='favorite_positions')
    position = models.PositiveIntegerField(default=0, db_index=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']
        unique_together = ('user', 'playlist')
        indexes = [
            models.Index(fields=['user', 'position'], name='music_favor_user_id_897cbf_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.position}: {self.playlist.name}"


class FavoriteSongPosition(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorite_song_positions')
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='favorite_positions')
    position = models.PositiveIntegerField(default=0, db_index=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']
        unique_together = ('user', 'song')
        indexes = [
            models.Index(fields=['user', 'position'], name='music_favor_user_id_fc4317_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.position}: {self.song.name}"


# 4. Comment Model
class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    liked_by = models.ManyToManyField(User, related_name='liked_comments', blank=True)
    good_count = models.IntegerField(default=0)
    bad_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.song.name} ({self.id})"


# 5. PlayHistory Model
class PlayHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='play_history')
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='play_history')
    played_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} played {self.song.name}"


# 7. Feedback Model
class Feedback(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_feedbacks')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_feedbacks')
    created_at = models.DateTimeField(auto_now_add=True)
    content = models.TextField()

    def __str__(self):
        return f"Feedback from {self.sender.username}"


# 8. Invitation Model
class Invitation(models.Model):
    code = models.IntegerField()

    def __str__(self):
        return str(self.code)


# --- SIGNALS FOR FILE MANAGEMENT & SYNC ---

@receiver(post_delete, sender=User)
def delete_auth_user(sender, instance, **kwargs):
    if instance.username:
        AuthUser.objects.filter(username=instance.username).delete()
    # Cleanup avatar
    if instance.avatar and 'default.jpeg' not in str(instance.avatar.name):
        delete_file_on_disk(instance.avatar)

@receiver(post_delete, sender=AuthUser)
def delete_custom_user(sender, instance, **kwargs):
    if instance.username:
        User.objects.filter(username=instance.username).delete()

@receiver(pre_save, sender=Song)
def song_pre_save_cleanup(sender, instance, **kwargs):
    instance.song_type = normalize_song_type(instance.song_type)
    if not instance.pk: return
    try:
        old_obj = Song.objects.get(pk=instance.pk)
    except Song.DoesNotExist: return

    # Cleanup cover if name changed
    if old_obj.cover.name != instance.cover.name:
        if old_obj.cover and 'default' not in str(old_obj.cover.name):
            delete_file_on_disk(old_obj.cover)
            
    # Cleanup audio if name changed
    if old_obj.download_link.name != instance.download_link.name:
        if old_obj.download_link:
            delete_file_on_disk(old_obj.download_link)

    # Cleanup lyrics if name changed
    if old_obj.lyrics.name != instance.lyrics.name:
        if old_obj.lyrics:
            delete_file_on_disk(old_obj.lyrics)

@receiver(post_delete, sender=Song)
def song_post_delete_cleanup(sender, instance, **kwargs):
    if instance.cover and 'default' not in str(instance.cover.name):
        delete_file_on_disk(instance.cover)
    if instance.download_link:
        delete_file_on_disk(instance.download_link)
    if instance.lyrics:
        delete_file_on_disk(instance.lyrics)

@receiver(post_save, sender=Song)
def song_post_save_rename(sender, instance, **kwargs):
    def get_safe_name(name):
        return re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')

    changed = False
    safe_name = get_safe_name(instance.name)
    
    # Standardize Cover
    if instance.cover and 'default' not in str(instance.cover.name):
        ext = instance.cover.name.split('.')[-1]
        expected_name = f"covers/{instance.id}_{safe_name}.{ext}"
        if instance.cover.name != expected_name:
            if instance.cover.storage.exists(instance.cover.name):
                old_path = instance.cover.path
                new_path = os.path.join(settings.MEDIA_ROOT, expected_name)
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                if old_path != new_path:
                    try:
                        if os.path.exists(new_path): os.remove(new_path)
                        os.rename(old_path, new_path)
                        instance.cover.name = expected_name
                        changed = True
                    except Exception as e:
                        print(f"[Models] Cover Rename failed: {e}")

    # Standardize Audio
    if instance.download_link:
        ext = instance.download_link.name.split('.')[-1]
        expected_name = f"songs/{instance.id}_{safe_name}.{ext}"
        if instance.download_link.name != expected_name:
            if instance.download_link.storage.exists(instance.download_link.name):
                old_path = instance.download_link.path
                new_path = os.path.join(settings.MEDIA_ROOT, expected_name)
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                if old_path != new_path:
                    try:
                        if os.path.exists(new_path): os.remove(new_path)
                        os.rename(old_path, new_path)
                        instance.download_link.name = expected_name
                        changed = True
                    except Exception as e:
                        print(f"[Models] Audio Rename failed: {e}")

    # Standardize Lyrics
    if instance.lyrics:
        ext = instance.lyrics.name.split('.')[-1]
        expected_name = f"lyrics/{instance.id}_{safe_name}.{ext}"
        if instance.lyrics.name != expected_name:
            if instance.lyrics.storage.exists(instance.lyrics.name):
                old_path = instance.lyrics.path
                new_path = os.path.join(settings.MEDIA_ROOT, expected_name)
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                if old_path != new_path:
                    try:
                        if os.path.exists(new_path): os.remove(new_path)
                        os.rename(old_path, new_path)
                        instance.lyrics.name = expected_name
                        changed = True
                    except Exception as e:
                        print(f"[Models] Lyrics Rename failed: {e}")

    if changed:
        Song.objects.filter(pk=instance.pk).update(
            cover=instance.cover.name, 
            download_link=instance.download_link.name,
            lyrics=instance.lyrics.name
        )

@receiver(pre_save, sender=Playlist)
def playlist_pre_save_cleanup(sender, instance, **kwargs):
    if not instance.pk: return
    try:
        old_obj = Playlist.objects.get(pk=instance.pk)
    except Playlist.DoesNotExist: return
    if old_obj.cover.name != instance.cover.name:
        if old_obj.cover and 'default' not in str(old_obj.cover.name):
            delete_file_on_disk(old_obj.cover)

@receiver(post_delete, sender=Playlist)
def playlist_post_delete_cleanup(sender, instance, **kwargs):
    if instance.cover and 'default' not in str(instance.cover.name):
        delete_file_on_disk(instance.cover)

@receiver(post_save, sender=Playlist)
def playlist_post_save_rename(sender, instance, **kwargs):
    def get_safe_name(name):
        return re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')

    if not (instance.cover and 'default' not in str(instance.cover.name)):
        return

    safe_name = get_safe_name(instance.name)
    ext = instance.cover.name.split('.')[-1]
    expected_name = f"playlists/{instance.id}_{safe_name}.{ext}"
    if instance.cover.name != expected_name:
        if instance.cover.storage.exists(instance.cover.name):
            old_path = instance.cover.path
            new_path = os.path.join(settings.MEDIA_ROOT, expected_name)
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            if old_path != new_path:
                try:
                    if os.path.exists(new_path): os.remove(new_path)
                    os.rename(old_path, new_path)
                    Playlist.objects.filter(pk=instance.pk).update(cover=expected_name)
                except Exception as e:
                    print(f"[Models] Playlist cover rename failed: {e}")

@receiver(pre_save, sender=User)
def user_pre_save_cleanup(sender, instance, **kwargs):
    if not instance.pk: return
    try:
        old_user = User.objects.get(pk=instance.pk)
    except User.DoesNotExist: return
    if old_user.avatar.name != instance.avatar.name:
        if old_user.avatar and 'default.jpeg' not in str(old_user.avatar.name):
            delete_file_on_disk(old_user.avatar)
