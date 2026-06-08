from django.db import migrations, models
import django.db.models.deletion


def seed_favorite_playlist_positions(apps, schema_editor):
    User = apps.get_model('music', 'User')
    FavoritePlaylistPosition = apps.get_model('music', 'FavoritePlaylistPosition')

    for user in User.objects.all():
        playlists = user.favorited_playlists.all().order_by('id')
        FavoritePlaylistPosition.objects.bulk_create([
            FavoritePlaylistPosition(user=user, playlist=playlist, position=position)
            for position, playlist in enumerate(playlists, start=1)
        ], ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('music', '0024_playlist_position'),
    ]

    operations = [
        migrations.CreateModel(
            name='FavoritePlaylistPosition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField(db_index=True, default=0)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('playlist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorite_positions', to='music.playlist')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorite_playlist_positions', to='music.user')),
            ],
            options={
                'ordering': ['position', 'id'],
                'unique_together': {('user', 'playlist')},
                'indexes': [models.Index(fields=['user', 'position'], name='music_favor_user_id_897cbf_idx')],
            },
        ),
        migrations.RunPython(seed_favorite_playlist_positions, migrations.RunPython.noop),
    ]
