from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('chroniker', '0003_generic_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='OptionKey',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
            ],
        ),
        migrations.CreateModel(
            name='Option',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.CharField(max_length=255)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='chroniker.Job')),
                ('key', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='chroniker.OptionKey')),
            ],
            options={
                'unique_together': {('job', 'key', 'value')},
            },
        ),
    ]
