from django.db import migrations, models


PHASES = (
    ('dawn-mend', 'Dawn - Mend', 'dawn', 1),
    ('dawn-kindle', 'Dawn - Kindle', 'dawn', 2),
    ('dawn-bloom', 'Dawn - Bloom', 'dawn', 3),
    ('midnight-settle', 'Midnight - Settle', 'midnight', 1),
    ('midnight-deep', 'Midnight - Deep', 'midnight', 2),
    ('midnight-fade', 'Midnight - Fade', 'midnight', 3),
    ('mood-hold', 'Mood - Hold', 'mood', 1),
    ('mood-ease', 'Mood - Ease', 'mood', 2),
    ('mood-recover', 'Mood - Recover', 'mood', 3),
    ('study-approved', 'Study - Approved', 'study', 1),
)


def seed_program_phases(apps, schema_editor):
    ProgramPhase = apps.get_model('music', 'ProgramPhase')
    for slug, name, station, phase_order in PHASES:
        ProgramPhase.objects.update_or_create(
            slug=slug,
            defaults={
                'name': name,
                'station': station,
                'phase_order': phase_order,
            },
        )


def remove_program_phases(apps, schema_editor):
    ProgramPhase = apps.get_model('music', 'ProgramPhase')
    ProgramPhase.objects.filter(slug__in=[row[0] for row in PHASES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('music', '0027_song_created_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProgramPhase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=50, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('station', models.CharField(
                    choices=[
                        ('dawn', 'Dawn Blessing'),
                        ('midnight', 'Midnight Radio'),
                        ('mood', 'Mood Journal'),
                        ('study', 'Study Focus'),
                    ],
                    db_index=True,
                    max_length=20,
                )),
                ('phase_order', models.PositiveSmallIntegerField(default=1)),
            ],
            options={
                'ordering': ['station', 'phase_order', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='programphase',
            constraint=models.UniqueConstraint(
                fields=('station', 'phase_order'),
                name='unique_program_station_phase',
            ),
        ),
        migrations.AddField(
            model_name='song',
            name='program_phases',
            field=models.ManyToManyField(blank=True, related_name='songs', to='music.programphase'),
        ),
        migrations.RunPython(seed_program_phases, remove_program_phases),
    ]
