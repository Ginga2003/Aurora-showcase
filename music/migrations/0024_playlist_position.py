from django.db import migrations, models


def seed_playlist_positions(apps, schema_editor):
    Playlist = apps.get_model('music', 'Playlist')
    User = apps.get_model('music', 'User')
    for user in User.objects.all():
        for position, playlist in enumerate(Playlist.objects.filter(user=user).order_by('id'), start=1):
            playlist.position = position
            playlist.save(update_fields=['position'])


class Migration(migrations.Migration):

    dependencies = [
        ('music', '0023_favoritesongposition'),
    ]

    operations = [
        migrations.AddField(
            model_name='playlist',
            name='position',
            field=models.PositiveIntegerField(db_index=True, default=0),
        ),
        migrations.RunPython(seed_playlist_positions, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='playlist',
            options={'ordering': ['position', 'id']},
        ),
    ]
