# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chroniker', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='frequency',
            field=models.CharField(max_length=10, verbose_name='frequency', choices=[('YEARLY', 'Yearly'), ('MONTHLY', 'Monthly'), ('WEEKLY', 'Weekly'), ('DAILY', 'Daily'), ('HOURLY', 'Hourly'), ('MINUTELY', 'Minutely'), ('SECONDLY', 'Secondly')]),
        ),
        migrations.AlterField(
            model_name='job',
            name='hostname',
            field=models.CharField(max_length=700, blank=True, help_text='If given, ensures the job is only run on the server with the equivalent host name.<br/>Not setting any hostname will cause the job to be run on the first server that processes pending jobs.<br/> e.g. The hostname of this server is <b>7910f538ac86</b>.', null=True, verbose_name='target hostname'),
        ),
        migrations.AlterField(
            model_name='job',
            name='maximum_log_entries',
            field=models.PositiveIntegerField(help_text='The maximum number of most recent log entries to keep.<br/>A value of 0 keeps all log entries.', default=1000),
        ),
        migrations.AlterField(
            model_name='job',
            name='monitor_error_template',
            field=models.TextField(help_text='If this is a monitor, this is the template used to compose the error text email.<br/>Available variables: {{ job }} {{ stderr }} {{ url }}', blank=True, default='\nThe monitor "{{ job.name }}" has indicated a problem.\n\nPlease review this monitor at {{ url }}\n\n{{ job.monitor_description_safe }}\n\n{{ stderr }}\n', null=True),
        ),
        migrations.AlterField(
            model_name='jobdependency',
            name='dependee',
            field=models.ForeignKey(help_text='The thing that has other jobs waiting on it to complete.', related_name='dependents', to='chroniker.Job'),
        ),
        migrations.AlterField(
            model_name='jobdependency',
            name='dependent',
            field=models.ForeignKey(help_text='The thing that cannot run until another job completes.', related_name='dependencies', to='chroniker.Job'),
        ),
        migrations.AlterField(
            model_name='jobdependency',
            name='wait_for_completion',
            field=models.BooleanField(help_text='If checked, the dependent job will not run until the dependee job has completed.', default=True),
        ),
        migrations.AlterField(
            model_name='jobdependency',
            name='wait_for_next_run',
            field=models.BooleanField(help_text='If checked, the dependent job will not run until the dependee job has a next_run greater than its next_run.', default=True),
        ),
        migrations.AlterField(
            model_name='jobdependency',
            name='wait_for_success',
            field=models.BooleanField(help_text='If checked, the dependent job will not run until the dependee job has completed successfully.', default=True),
        ),
        migrations.AlterField(
            model_name='log',
            name='duration_seconds',
            field=models.PositiveIntegerField(db_index=True, blank=True, editable=False, null=True, verbose_name='duration (total seconds)'),
        ),
    ]
