# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=200, verbose_name='name')),
                ('frequency', models.CharField(max_length=10, verbose_name='frequency', choices=[(b'YEARLY', 'Yearly'), (b'MONTHLY', 'Monthly'), (b'WEEKLY', 'Weekly'), (b'DAILY', 'Daily'), (b'HOURLY', 'Hourly'), (b'MINUTELY', 'Minutely'), (b'SECONDLY', 'Secondly')])),
                ('params', models.TextField(help_text='Comma-separated list of <a href="http://labix.org/python-dateutil" target="_blank">rrule parameters</a>. e.g: interval:15', null=True, verbose_name='params', blank=True)),
                ('command', models.CharField(help_text='A valid django-admin command to run.', max_length=200, verbose_name='command', blank=True)),
                ('args', models.CharField(help_text='Space separated list; e.g: arg1 option1=True', max_length=200, verbose_name='args', blank=True)),
                ('raw_command', models.CharField(help_text='The raw shell command to run.\n            This is mutually exclusive with `command`.', max_length=1000, null=True, verbose_name='raw command', blank=True)),
                ('enabled', models.BooleanField(default=True, help_text='If checked, this job will be run automatically according\n            to the frequency options.')),
                ('next_run', models.DateTimeField(help_text="If you don't set this it will be determined automatically", null=True, verbose_name='next run', blank=True)),
                ('last_run_start_timestamp', models.DateTimeField(verbose_name='last run start timestamp', null=True, editable=False, blank=True)),
                ('last_run', models.DateTimeField(verbose_name='last run end timestamp', null=True, editable=False, blank=True)),
                ('last_heartbeat', models.DateTimeField(verbose_name='last heartbeat', null=True, editable=False, blank=True)),
                ('is_running', models.BooleanField(default=False)),
                ('last_run_successful', models.NullBooleanField(verbose_name='success', editable=False)),
                ('email_errors_to_subscribers', models.BooleanField(default=True, help_text='If checked, the stdout and stderr of a job will be emailed to the subscribers if an error occur.')),
                ('email_success_to_subscribers', models.BooleanField(default=False, help_text='If checked, the stdout of a job will be emailed to the subscribers if not errors occur.')),
                ('lock_file', models.CharField(max_length=255, editable=False, blank=True)),
                ('force_run', models.BooleanField(default=False, help_text='If checked, then this job will be run immediately.')),
                ('force_stop', models.BooleanField(default=False, help_text='If checked, and running then this job will be stopped.')),
                ('timeout_seconds', models.PositiveIntegerField(default=0, help_text='When non-zero, the job will be forcibly killed if\n            running for more than this amount of time.')),
                ('hostname', models.CharField(help_text='If given, ensures the job is only run on the server with the equivalent host name.<br/>Not setting any hostname will cause the job to be run on the first server that processes pending jobs.<br/> e.g. The hostname of this server is <b>kronos</b>.', max_length=700, null=True, verbose_name=b'target hostname', blank=True)),
                ('current_hostname', models.CharField(help_text='The name of the host currently running the job.', max_length=700, null=True, editable=False, blank=True)),
                ('current_pid', models.CharField(editable=False, max_length=50, blank=True, help_text='The ID of the process currently running the job.', null=True, db_index=True)),
                ('total_parts_complete', models.PositiveIntegerField(default=0, help_text='The total number of complete parts.', editable=False)),
                ('total_parts', models.PositiveIntegerField(default=0, help_text='The total number of parts of the task.', editable=False)),
                ('is_monitor', models.BooleanField(default=False, help_text='If checked, will appear in the monitors section.')),
                ('monitor_url', models.CharField(help_text='URL provided to further explain the monitor.', max_length=255, null=True, blank=True)),
                ('monitor_error_template', models.TextField(default=b'\nThe monitor "{{ job.name }}" has indicated a problem.\n\nPlease review this monitor at {{ url }}\n\n{{ job.monitor_description_safe }}\n\n{{ stderr }}\n', help_text='If this is a monitor, this is the template used to compose the error text email.<br/>Available variables: {{ job }} {{ stderr }} {{ url }}', null=True, blank=True)),
                ('monitor_description', models.TextField(help_text="An explanation of the monitor's purpose.", null=True, blank=True)),
                ('monitor_records', models.IntegerField(help_text='The number of records that need attention.', null=True, editable=False, blank=True)),
                ('maximum_log_entries', models.PositiveIntegerField(default=1000, help_text=b'The maximum number of most recent log entries to keep.<br/>A value of 0 keeps all log entries.')),
                ('log_stdout', models.BooleanField(default=True, help_text='If checked, all characters printed to stdout will be\n            saved in a log record.')),
                ('log_stderr', models.BooleanField(default=True, help_text='If checked, all characters printed to stderr will be\n            saved in a log record.')),
                ('subscribers', models.ManyToManyField(related_name='subscribed_jobs', to=settings.AUTH_USER_MODEL, blank=True)),
            ],
            options={
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='JobDependency',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('wait_for_completion', models.BooleanField(default=True, help_text=b'If checked, the dependent job will not run until the dependee job has completed.')),
                ('wait_for_success', models.BooleanField(default=True, help_text=b'If checked, the dependent job will not run until the dependee job has completed successfully.')),
                ('wait_for_next_run', models.BooleanField(default=True, help_text=b'If checked, the dependent job will not run until the dependee job has a next_run greater than its next_run.')),
                ('dependee', models.ForeignKey(related_name='dependents', to='chroniker.Job', help_text=b'The thing that has other jobs waiting on it to complete.')),
                ('dependent', models.ForeignKey(related_name='dependencies', to='chroniker.Job', help_text=b'The thing that cannot run until another job completes.')),
            ],
            options={
                'verbose_name_plural': 'job dependencies',
            },
        ),
        migrations.CreateModel(
            name='Log',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('run_start_datetime', models.DateTimeField(default=django.utils.timezone.now, editable=False, db_index=True)),
                ('run_end_datetime', models.DateTimeField(db_index=True, null=True, editable=False, blank=True)),
                ('duration_seconds', models.PositiveIntegerField(db_index=True, verbose_name=b'duration (total seconds)', null=True, editable=False, blank=True)),
                ('stdout', models.TextField(blank=True)),
                ('stderr', models.TextField(blank=True)),
                ('hostname', models.CharField(help_text='The hostname this job was executed on.', max_length=700, null=True, editable=False, blank=True)),
                ('success', models.BooleanField(default=True, db_index=True, editable=False)),
                ('on_time', models.BooleanField(default=True, help_text='If true, indicates job completed of its own accord.\n            If false, the job exceeded a timeout threshold and was forcibly\n            killed.', db_index=True, editable=False)),
                ('job', models.ForeignKey(related_name='logs', to='chroniker.Job')),
            ],
            options={
                'ordering': ('-run_start_datetime',),
            },
        ),
        migrations.CreateModel(
            name='Monitor',
            fields=[
            ],
            options={
                'proxy': True,
            },
            bases=('chroniker.job',),
        ),
        migrations.AlterUniqueTogether(
            name='jobdependency',
            unique_together=set([('dependent', 'dependee')]),
        ),
    ]
