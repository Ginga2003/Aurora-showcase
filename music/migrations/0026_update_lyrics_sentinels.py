from django.db import migrations, models
import music.models


def replace_legacy_puremusic_marker(apps, schema_editor):
    Song = apps.get_model('music', 'Song')
    Song.objects.filter(lyrics='1145141919810').update(lyrics='puremusic')


def restore_legacy_puremusic_marker(apps, schema_editor):
    Song = apps.get_model('music', 'Song')
    Song.objects.filter(lyrics='puremusic').update(lyrics='1145141919810')


class Migration(migrations.Migration):

    dependencies = [
        ('music', '0025_favoriteplaylistposition'),
    ]

    operations = [
        migrations.AlterField(
            model_name='song',
            name='lyrics',
            field=models.FileField(blank=True, default='puremusic', null=True, upload_to=music.models.song_lrc_path),
        ),
        migrations.RunPython(replace_legacy_puremusic_marker, restore_legacy_puremusic_marker),
    ]
