import re
import wave
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User as AuthUser
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from music.models import Comment, FavoriteSongPosition, PlayHistory, Playlist, PlaylistSong, Song, User


SAMPLE_TRACKS = [
    ("Northline", "Demo Sessions", "Aurora Lab", "Electronic | Ambient", "2026-01-14", 1840, 0),
    ("Glass Route", "Demo Sessions", "Aurora Lab | Metro Unit", "Synth | Pop", "2026-02-02", 1665, 1),
    ("Midnight Index", "Catalog Notes", "Index Team", "Lo-fi | Instrumental", "2026-02-18", 1390, 2),
    ("Paper Signal", "Catalog Notes", "Index Team", "Acoustic | Pop", "2026-03-03", 1120, 3),
    ("Quiet Build", "Release Queue", "Build Room", "Indie | Ambient", "2026-03-21", 980, 5),
    ("After Deploy", "Release Queue", "Build Room", "Electronic | Instrumental", "2026-04-09", 865, 9),
]


class Command(BaseCommand):
    help = "Seed the showcase copy with a demo user and optional fake screenshot data."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--email", default="demo@example.com")
        parser.add_argument("--password", default="demo123456")
        parser.add_argument("--with-sample-content", action="store_true")
        parser.add_argument("--with-admin", action="store_true")
        parser.add_argument("--admin-username", default="admin")
        parser.add_argument("--admin-email", default="admin@example.com")
        parser.add_argument("--admin-password", default="admin123456")

    def handle(self, *args, **options):
        call_command(
            "reset_showcase",
            username=options["username"],
            email=options["email"],
            password=options["password"],
            noinput=True,
            verbosity=0,
        )

        admin_message = ""
        if options["with_admin"]:
            self._ensure_admin_user(
                options["admin_username"],
                options["admin_email"],
                options["admin_password"],
            )
            admin_message = f", admin={options['admin_username']}"

        if not options["with_sample_content"]:
            self.stdout.write(self.style.SUCCESS(f"Showcase seed complete: user={options['username']}{admin_message}, songs=0, playlists=0."))
            return

        profile = User.objects.get(username=options["username"])
        songs = self._create_sample_songs()
        self._create_sample_playlist(profile, songs)
        self._create_sample_activity(profile, songs)
        self.stdout.write(self.style.SUCCESS(f"Showcase sample content created: {len(songs)} fake songs, 1 playlist{admin_message}."))

    def _create_sample_songs(self):
        now = timezone.now()
        songs = []
        for index, (name, album, arrangement, song_type, release_date, views, upload_days_ago) in enumerate(SAMPLE_TRACKS):
            uploaded_at = now - timedelta(days=upload_days_ago, minutes=index * 11)
            song = Song.objects.create(
                name=name,
                album=album,
                arrangement=arrangement,
                song_type=song_type,
                introduction="Synthetic showcase metadata for screenshots only.",
                release_date=date.fromisoformat(release_date),
                views=views,
            )
            audio_name = f"songs/{song.id}_{self._safe_name(song.name)}.wav"
            self._write_silent_wav(Path(settings.MEDIA_ROOT) / audio_name)
            Song.objects.filter(pk=song.pk).update(download_link=audio_name, created_at=uploaded_at)
            song.download_link = audio_name
            song.created_at = uploaded_at
            songs.append(song)
        return songs

    def _create_sample_playlist(self, user, songs):
        now = timezone.now()
        playlist = Playlist.objects.create(
            user=user,
            name="Showcase Mix",
            introduction="A fake playlist used only for portfolio screenshots.",
            is_private=False,
            views=256,
            position=1,
        )
        Playlist.objects.filter(pk=playlist.pk).update(created_at=now - timedelta(days=1, hours=2))
        playlist.songs.set(songs[:4])
        PlaylistSong.objects.bulk_create(
            [PlaylistSong(playlist=playlist, song=song, position=index) for index, song in enumerate(songs[:4], start=1)]
        )

    def _create_sample_activity(self, user, songs):
        now = timezone.now()
        favorite_songs = [songs[0], songs[2], songs[4]]
        user.favorite_songs.set(favorite_songs)
        FavoriteSongPosition.objects.bulk_create(
            [FavoriteSongPosition(user=user, song=song, position=index) for index, song in enumerate(favorite_songs, start=1)]
        )
        play_events = [
            (songs[0], 0, 1),
            (songs[1], 0, 4),
            (songs[0], 1, 2),
            (songs[2], 1, 7),
            (songs[3], 2, 5),
            (songs[0], 3, 3),
            (songs[4], 4, 2),
            (songs[5], 8, 1),
        ]
        for song, days_ago, hours_ago in play_events:
            history = PlayHistory.objects.create(user=user, song=song)
            PlayHistory.objects.filter(pk=history.pk).update(played_at=now - timedelta(days=days_ago, hours=hours_ago))

        comment = Comment.objects.create(user=user, song=songs[0], content="The queue and playlist flows are ready for a short demo.")
        Comment.objects.filter(pk=comment.pk).update(created_at=now - timedelta(hours=6))

    def _ensure_admin_user(self, username, email, password):
        admin_user, _ = AuthUser.objects.update_or_create(
            username=username,
            defaults={
                "email": email,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin_user.set_password(password)
        admin_user.save()

    def _safe_name(self, value):
        return re.sub(r"[^\w\s-]", "", value).strip().replace(" ", "_")

    def _write_silent_wav(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 8000
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * sample_rate)
