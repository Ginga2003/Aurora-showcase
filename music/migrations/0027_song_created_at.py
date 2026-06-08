from datetime import datetime, time

from django.db import migrations, models
from django.utils import timezone


def backfill_song_created_at(apps, schema_editor):
    Song = apps.get_model('music', 'Song')
    fallback = timezone.now()

    for song in Song.objects.filter(created_at__isnull=True):
        if song.release_date:
            created_at = timezone.make_aware(datetime.combine(song.release_date, time(hour=12)))
        else:
            created_at = fallback
        Song.objects.filter(pk=song.pk).update(created_at=created_at)


class Migration(migrations.Migration):

    dependencies = [
        ('music', '0026_update_lyrics_sentinels'),
    ]

    operations = [
        migrations.AddField(
            model_name='song',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_song_created_at, migrations.RunPython.noop),
    ]
