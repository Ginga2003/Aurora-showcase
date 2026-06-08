from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User as AuthUser
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from music.models import (
    Comment,
    FavoritePlaylistPosition,
    FavoriteSongPosition,
    Feedback,
    Invitation,
    PlayHistory,
    Playlist,
    PlaylistSong,
    Song,
    User,
)


PLACEHOLDER_FILES = {
    "avatars": {"default.jpeg"},
    "covers": {"default_cover.jpg"},
    "lyrics": set(),
    "playlists": {"default_playlist.png", "Favourite.png"},
    "songs": set(),
}


class Command(BaseCommand):
    help = "Reset the sanitized showcase database to one demo user and no songs."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--email", default="demo@example.com")
        parser.add_argument("--password", default="demo123456")
        parser.add_argument("--noinput", action="store_true")

    def handle(self, *args, **options):
        username = options["username"]
        email = options["email"]
        password = options["password"]

        if not options["noinput"]:
            answer = input("This will delete showcase runtime data. Type RESET to continue: ")
            if answer != "RESET":
                self.stdout.write(self.style.WARNING("Reset cancelled."))
                return

        with transaction.atomic():
            self._delete_domain_data()
            self._ensure_single_user(username, email, password)

        self._remove_runtime_media()
        self.stdout.write(self.style.SUCCESS(f"Showcase reset complete: user={username}, songs=0, playlists=0."))

    def _delete_domain_data(self):
        Comment.objects.all().delete()
        PlayHistory.objects.all().delete()
        Feedback.objects.all().delete()
        Invitation.objects.all().delete()
        FavoriteSongPosition.objects.all().delete()
        FavoritePlaylistPosition.objects.all().delete()
        PlaylistSong.objects.all().delete()
        Playlist.objects.all().delete()
        Song.objects.all().delete()

    def _ensure_single_user(self, username, email, password):
        AuthUser.objects.exclude(username=username).delete()
        User.objects.exclude(username=username).delete()

        auth_user, _ = AuthUser.objects.update_or_create(
            username=username,
            defaults={"email": email, "is_active": True, "is_staff": True, "is_superuser": True},
        )
        auth_user.set_password(password)
        auth_user.save()

        User.objects.update_or_create(
            username=username,
            defaults={
                "email": email,
                "password": make_password(password),
                "status": "Active",
                "avatar": "avatars/default.jpeg",
            },
        )

    def _remove_runtime_media(self):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        media_root.mkdir(parents=True, exist_ok=True)

        for subdir, keep_names in PLACEHOLDER_FILES.items():
            target_dir = (media_root / subdir).resolve()
            try:
                target_dir.relative_to(media_root)
            except ValueError as exc:
                raise CommandError(f"Unsafe media path: {target_dir}") from exc
            target_dir.mkdir(parents=True, exist_ok=True)

            for path in sorted(target_dir.rglob("*"), reverse=True):
                if path.is_dir():
                    try:
                        path.rmdir()
                    except OSError:
                        pass
                    continue
                if path.name in keep_names:
                    continue
                path.unlink(missing_ok=True)
