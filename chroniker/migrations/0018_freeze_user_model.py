# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


# Safe User import for Django < 1.5
try:
    from django.contrib.auth import get_user_model
except ImportError:
    from django.contrib.auth.models import User
else:
    User = get_user_model()

# With the default User model these will be 'auth.User' and 'auth.user'
# so instead of using orm['auth.User'] we can use orm[user_orm_label]
user_orm_label = '%s.%s' % (User._meta.app_label, User._meta.object_name)
user_model_label = '%s.%s' % (User._meta.app_label, User._meta.module_name)
user_column_name = '%s_id' % User._meta.module_name

class Migration(SchemaMigration):

    def forwards(self, orm):
        # Based on the solution at:
        # http://kevindias.com/writing/django-custom-user-models-south-and-reusable-apps/
        # Update: We will need to update the table column too
        # as the 'through' workaround will require changes in admin fieldsets too
        # However renaming won't cause any changes to existing deployments
        db.rename_column('chroniker_job_subscribers', 'user_id', user_column_name)


    def backwards(self, orm):
        db.rename_column('chroniker_job_subscribers', user_column_name, 'user_id')

    models = {
        u'chroniker.job': {
            'Meta': {'ordering': "('name',)", 'object_name': 'Job'},
            'args': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'}),
            'command': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'}),
            'current_hostname': ('django.db.models.fields.CharField', [], {'max_length': '700', 'null': 'True', 'blank': 'True'}),
            'current_pid': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'email_errors_to_subscribers': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'email_success_to_subscribers': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'enabled': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'force_run': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'force_stop': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'frequency': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'hostname': ('django.db.models.fields.CharField', [], {'max_length': '700', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_monitor': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_running': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_heartbeat': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'last_run': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'last_run_start_timestamp': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'last_run_successful': ('django.db.models.fields.NullBooleanField', [], {'null': 'True', 'blank': 'True'}),
            'lock_file': ('django.db.models.fields.CharField', [], {'max_length': '255', 'blank': 'True'}),
            'log_stderr': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'log_stdout': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'maximum_log_entries': ('django.db.models.fields.PositiveIntegerField', [], {'default': '1000'}),
            'monitor_description': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'monitor_error_template': ('django.db.models.fields.TextField', [], {'default': '\'\\nThe monitor "{{ job.name }}" has indicated a problem.\\n\\nPlease review this monitor at {{ url }}\\n\\n{{ job.monitor_description_safe }}\\n\\n{{ stderr }}\\n\'', 'null': 'True', 'blank': 'True'}),
            'monitor_records': ('django.db.models.fields.IntegerField', [], {'null': 'True', 'blank': 'True'}),
            'monitor_url': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'next_run': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'params': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'raw_command': ('django.db.models.fields.CharField', [], {'max_length': '1000', 'null': 'True', 'blank': 'True'}),
            'subscribers': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'subscribed_jobs'", 'blank': 'True', 'through': u"orm['chroniker.SubscribedJob']", 'to': u"orm['%s']" % user_orm_label}),
            'timeout_seconds': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0'}),
            'total_parts': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0'}),
            'total_parts_complete': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0'})
        },
        u'chroniker.jobdependency': {
            'Meta': {'unique_together': "(('dependent', 'dependee'),)", 'object_name': 'JobDependency'},
            'dependee': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'dependents'", 'to': u"orm['chroniker.Job']"}),
            'dependent': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'dependencies'", 'to': u"orm['chroniker.Job']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'wait_for_completion': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'wait_for_next_run': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'wait_for_success': ('django.db.models.fields.BooleanField', [], {'default': 'True'})
        },
        u'chroniker.log': {
            'Meta': {'ordering': "('-run_start_datetime',)", 'object_name': 'Log'},
            'duration_seconds': ('django.db.models.fields.PositiveIntegerField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'hostname': ('django.db.models.fields.CharField', [], {'max_length': '700', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'job': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'logs'", 'to': u"orm['chroniker.Job']"}),
            'on_time': ('django.db.models.fields.BooleanField', [], {'default': 'True', 'db_index': 'True'}),
            'run_end_datetime': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'run_start_datetime': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now', 'db_index': 'True'}),
            'stderr': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'stdout': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'success': ('django.db.models.fields.BooleanField', [], {'default': 'True', 'db_index': 'True'})
        },
        u'chroniker.subscribedjob': {
            'Meta': {'object_name': 'SubscribedJob', 'db_table': "'chroniker_job_subscribers'"},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'job': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['chroniker.Job']"}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['%s']" % user_orm_label, 'db_column': "'user_id'"})
        },
        user_model_label: {
            'Meta': {'object_name': User.__name__},
            User._meta.pk.attname: (
                'django.db.models.fields.AutoField', [],
                {'primary_key': 'True',
                'db_column': "'%s'" % User._meta.pk.column}
            ),
        }
    }

    complete_apps = ['chroniker']
