import logging
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import traceback

from datetime import datetime, timedelta
from dateutil import rrule
from StringIO import StringIO
import threading
try:
    import thread
except ImportError:
    import dummy_thread as thread

import settings as _settings

import django
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.core.management import call_command
from django.db import models, connection, transaction
from django.db.models import Q
from django.template import loader, Context, Template
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.safestring import mark_safe
from django.utils.timesince import timeuntil
from django.utils.translation import ungettext, ugettext, ugettext_lazy as _
from django.contrib.sites.models import get_current_site
from django.core.exceptions import ValidationError

import chroniker.constants as const
import chroniker.utils

logger = logging.getLogger('chroniker.models')

_state = {} # {thread_ident:job_id}
_state_heartbeat = {} # {thread_ident:heartbeat thread object}

def order_by_dependencies(j1, j2):
    """
    Compares jobs so that jobs that are depended upon by another
    process are ordered first.
    """
    # Return negative if x<y, zero if x==y, positive if x>y.
    # If j1 depends on the completion of j2 then order j2 first.
    if j1.dependencies.filter(dependee=j2).count():
        ret = 1
    elif j1.dependents.filter(dependent=j2).count():
        ret = -1
    elif j2.dependencies.filter(dependee=j1).count():
        ret = -1
    elif j2.dependents.filter(dependent=j1).count():
        ret = 1
    else:
        ret = 0
    return ret

def get_current_job():
    """
    Retrieves the job associated with the current thread.
    """
    thread_ident = thread.get_ident()
    if thread_ident in _state:
        try:
            job_id = _state.get(thread_ident)
            return Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return

def get_current_heartbeat():
    thread_ident = thread.get_ident()
    return _state_heartbeat.get(thread_ident, None)

def set_current_job(job):
    """
    Associates a job with the current thread.
    """
    try:
        job_id = int(job)
    except ValueError, e:
        job_id = job.id
    except TypeError, e:
        job_id = job.id
    thread_ident = thread.get_ident()
    if thread_ident not in _state:
        _state[thread_ident] = job_id

def set_current_heartbeat(obj):
    """
    Associates a heartbeat with the current thread.
    """
    thread_ident = thread.get_ident()
    if thread_ident not in _state_heartbeat:
        _state_heartbeat[thread_ident] = obj

class JobHeartbeatThread(threading.Thread):
    """
    A very simple thread that updates a temporary "lock" file every second.
    If the ``Job`` that we are associated with gets killed off, then the file
    will no longer be updated and after ``CHRONIKER_LOCK_TIMEOUT`` seconds,
    we assume the ``Job`` has terminated.
    
    The heartbeat should be started with the ``start`` method and once the
    ``Job`` is completed it should be stopped by calling the ``stop`` method.
    """
    
    daemon = True
    
    halt = False

    def __init__(self, job_id, lock, *args, **kwargs):
        self.job_id = job_id
        self.lock = lock
        self.lock_file = tempfile.NamedTemporaryFile()
        self.original_pid = os.getpid()
        set_current_job(job_id)
        set_current_heartbeat(self)
        threading.Thread.__init__(self, *args, **kwargs)

    def run(self):
        """
        Do not call this directly; call ``start()`` instead.
        """
        check_freq_secs = 5
        while not self.halt:
            
            # If the current PID doesn't match the one we started with
            # then that means we were forked by a subprocess launched by the
            # job. In this case, we're a clone, so immediately exit so we don't
            # conflict with the thread in the original process.
            if os.getpid() != self.original_pid:
                return
            
            #print 'Heartbeat check...'
            self.lock_file.seek(0)
            self.lock_file.write(str(time.time()))
            self.lock_file.flush()
            
            # Check job status and save heartbeat timestamp.
            self.lock.acquire()
            Job.objects.update()
            job = Job.objects.only('id', 'force_stop').get(id=self.job_id)
            force_stop = job.force_stop
            Job.objects.filter(id=self.job_id).update(
                last_heartbeat = timezone.now(),
                force_stop = False,
                force_run = False,
            )
            self.lock.release()
            
            # If we noticed we're being forced to stop, then interrupt
            # the entire process.
            if force_stop:
                self.halt = True
                thread.interrupt_main()
                return
            
            time.sleep(check_freq_secs)
            
        set_current_heartbeat(None)
    
    def stop(self):
        """
        Call this to stop the heartbeat.
        """
        self.halt = True
        while self.is_alive():
            time.sleep(.1)
        self.lock_file.close()
        
    def update_progress(self, total_parts, total_parts_complete, lock=True):
        """
        JobHeartbeatThread
        """
        if lock:
            self.lock.acquire()
#        print '!'*80
#        import thread
#        thread_ident = thread.get_ident()
#        print 'self1:',self
#        print 'id1:',id(self)
#        print 'thread1:',thread_ident
#        print 'job_id1:',self.job_id
#        print 'pid1:',os.getpid()
#        print 'total_parts1:',total_parts
#        print 'total_parts_complete1:',total_parts_complete
#        print '!'*80
        Job.objects.filter(id=self.job_id).update(
            total_parts = total_parts,
            total_parts_complete = total_parts_complete,
        )
        if lock:
            self.lock.release()

class JobDependency(models.Model):
    """
    Represents a scheduling dependency between two jobs.
    """
    
    dependent = models.ForeignKey(
        'Job',
        related_name='dependencies',
        help_text='The thing that cannot run until another job completes.')
    
    dependee = models.ForeignKey(
        'Job',
        related_name='dependents',
        help_text='The thing that has other jobs waiting on it to complete.')
    
    wait_for_completion = models.BooleanField(
        default=True,
        help_text='If checked, the dependent job will not run until ' + \
            'the dependee job has completed.')
    
    wait_for_success = models.BooleanField(
        default=True,
        help_text='If checked, the dependent job will not run until ' + \
            'the dependee job has completed successfully.')
    
    wait_for_next_run = models.BooleanField(
        default=True,
        help_text='If checked, the dependent job will not run until ' + \
            'the dependee job has a next_run greater than its next_run.')
    
    def criteria_met(self, running_ids=None):
        if running_ids is None:
            running_ids = set()
        if self.wait_for_completion and (self.dependee.is_running or self.dependee.id in running_ids):
            # Don't run until our dependency completes.
#            print '"%s": Dependee "%s" is still running.' \
#                % (self.dependent.name, self.dependee.name,)
            return False
        if self.wait_for_success and not self.dependee.last_run_successful:
            # Don't run until our dependency completes successfully.
#            print '"%s": Dependee "%s" failed its last run.' \
#                % (self.dependent.name, self.dependee.name,)
            return False
        if self.wait_for_next_run:
            # Don't run until our dependency is scheduled until after
            # our next run.
            if not self.dependent.next_run:
#                print '"%s": Our next scheduled run has not been set.' \
#                    % (self.dependent.name,)
                return False
            if not self.dependee.next_run:
#                print '"%s": Dependee "%s" has not been scheduled to run.' \
#                    % (self.dependent.name, self.dependee.name,)
                return False
            if self.dependee.next_run < self.dependent.next_run:
#                print '"%s": Dependee "%s" has not yet run before us.' \
#                    % (self.dependent.name, self.dependee.name,)
                return False
        return True
    criteria_met.boolean = True
    
    class Meta:
        verbose_name_plural = 'job dependencies'
        unique_together = (
            ('dependent', 'dependee'),
        )
        
    def __unicode__(self):
        return unicode(self.dependent) + ' -> ' + unicode(self.dependee)

class JobManager(models.Manager):
    
    def due(self, job=None, check_running=True):
        """
        Returns a ``QuerySet`` of all jobs waiting to be run.  NOTE: this may
        return ``Job``s that are still currently running; it is your
        responsibility to call ``Job.check_is_running()`` to determine whether
        or not the ``Job`` actually needs to be run.
        """
        
        # Lock the Job record if possible with the backend.
        # https://docs.djangoproject.com/en/dev/ref/models/querysets/#select-for-update
        # Note, select_for_update() may not be supported, such as with MySQL.
        # Those backends will need to use an explicit backend-specific locking
        # mechanism.
        if settings.CHRONIKER_SELECT_FOR_UPDATE:
            q = self.select_for_update(nowait=False)
        else:
            q = self.all()
        q = q.filter(Q(next_run__lte=timezone.now()) | Q(force_run=True))
        q = q.filter(
            Q(hostname__isnull=True) | \
            Q(hostname='') | \
            Q(hostname=socket.gethostname()))
        q = q.filter(enabled=True)
        if check_running:
            q = q.filter(is_running=False)
        if job is not None:
            if isinstance(job, int):
                job = job.id
            q = q.filter(id=job.id)
        return q

    def due_with_met_dependencies(self, jobs=[]):
        """
        Iterates over the results of due(), ignoring jobs
        that are dependent on another job that is also due.
        """
        
        # Fixes the "Lost connection to MySQL server during query" error when
        # called from cron command?
        connection.close()
        
        skipped_job_ids = set()
        for job in self.due():
            if jobs and job.id not in jobs:
                #print 'Skipping job %i (%s) because jobs are limited to %s.' % (job.id, job, ', '.join(map(str, jobs)))
                skipped_job_ids.add(job.id)
                continue
            
            deps = job.dependencies.all()
            valid = True
            
            if job.check_is_running():
                #print 'Skipping job %i (%s) which is already running.' % (job.id, job)
                continue
            
            failed_dep = None
            for dep in deps:
                if dep.dependee.id in skipped_job_ids:
                    continue
                #elif dep.wait_for_completion and dep.dependee.is_due():
                elif not dep.criteria_met():
                    valid = False
                    failed_dep = dep
                    break
                
            if not valid:
                #print 'Skipping job %i (%s) which is dependent on a due job %i (%s).' \
                #    % (job.id, job, failed_dep.dependee.id, failed_dep.dependee)
                skipped_job_ids.add(job.id)
                continue
            
            #TODO:remove? redundant?
            if not job.dependencies_met():
                #print 'Skipping job %i (%s) which has unmet dependencies.' % (job.id, job)
                skipped_job_ids.add(job.id)
                continue
            
            yield job

    def due_with_met_dependencies_ordered(self, jobs=[]):
        """
        Returns a list of jobs sorted by dependency, with dependents after
        all their dependees.
        """
        lst = list(self.due_with_met_dependencies(jobs=jobs))
        lst.sort(cmp=order_by_dependencies)
        return lst

    def stale(self):
        q = self.filter(is_running=True)
        q = q.filter(
            Q(last_heartbeat__isnull=True) | 
            Q(last_heartbeat__lt=timezone.now() - timedelta(minutes=settings.CHRONIKER_STALE_MINUTES)))
        return q
    
    def all_running(self):
        return self.filter(is_running=True)
    
    @transaction.commit_manually
    def end_all_stale(self):
        """
        Marks as complete but failed, and attempts to kill the process
        if still running, any job that's failed to report its status within
        the alotted threshold.
        """
        try:
            q = self.stale()
            total = q.count()
            print '%i total stale jobs.' % (total,)
            for job in q.iterator():
                print 'Checking stale job %i <%s>...' % (job.id, job,)
                
                # If we know the PID and it's running locally, and the process
                # appears inactive, then attempt to forcibly kill the job.
                if job.current_pid and job.current_hostname \
                and job.current_hostname == socket.gethostname():
                    if chroniker.utils.pid_exists(job.current_pid):
#                        cpu_usage = chroniker.utils.get_cpu_usage(job.current_pid)
#                        if cpu_usage:
#                            print 'Process with PID %s is still consuming CPU so keeping alive for now.' % (job.current_pid,)
#                            continue
#                        else:
                        print 'Killing process %s...' % (job.current_pid,)
                        chroniker.utils.kill_process(job.current_pid)
                        #TODO:record log entry
                    else:
                        print 'Process with PID %s is not running.' % (job.current_pid,)
                else:
                    print 'Process with PID %s is not elligible for killing.' % (job.current_pid,)
                
                job.is_running = False
                job.last_run_successful = False
                job.save()
                transaction.commit()
                
                Log.objects.create(
                    job = job,
                    run_start_datetime = job.last_run_start_timestamp or timezone.now(),
                    run_end_datetime = timezone.now(),
                    hostname = socket.gethostname(),
                    stdout = '',
                    stderr = 'Job became stale and was marked as terminated.',
                    success = False,
                )
                transaction.commit()
        except:
            transaction.rollback()
            raise
        else:
            transaction.commit()

class Job(models.Model):
    """
    A recurring ``django-admin`` command to be run.
    """
    
    objects = JobManager()
    
    name = models.CharField(
        _("name"),
        max_length=200)
    
    frequency = models.CharField(
        _("frequency"),
        choices=const.FREQ_CHOICES,
        max_length=10)
    
    params = models.TextField(
        _("params"),
        null=True,
        blank=True,
        help_text=_(
            'Comma-separated list of '
            '<a href="http://labix.org/python-dateutil" '
            'target="_blank">rrule parameters</a>. '
            'e.g: interval:15'))
    
    command = models.CharField(
        _("command"),
        max_length=200,
        blank=True,
        help_text=_("A valid django-admin command to run."))
    
    args = models.CharField(
        _("args"),
        max_length=200,
        blank=True,
        help_text=_("Space separated list; e.g: arg1 option1=True"))
    
    raw_command = models.CharField(
        _("raw command"),
        max_length=1000,
        blank=True,
        null=True,
        help_text=_("A raw shell command to run. This is mutually exclusive with `command`."))
    
    enabled = models.BooleanField(
        default=True,
        help_text=_('''If checked, this job will be run automatically according
            to the frequency options.'''))
    
    next_run = models.DateTimeField(
        _("next run"),
        blank=True,
        null=True,
        help_text=_("If you don't set this it will"
            " be determined automatically"))
    
    last_run_start_timestamp = models.DateTimeField(
        _("last run start timestamp"),
        editable=False,
        blank=True,
        null=True)
    
    last_run = models.DateTimeField(
        _("last run end timestamp"),
        editable=False,
        blank=True,
        null=True)
    
    last_heartbeat = models.DateTimeField(
        _("last heartbeat"),
        editable=False,
        blank=True,
        null=True)
    
    is_running = models.BooleanField(
        default=False,
        editable=True,
    )
    
    last_run_successful = models.NullBooleanField(
        _('success'),
        blank=True,
        null=True,
        editable=False)
    
    subscribers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='subscribed_jobs',
        blank=True,
        limit_choices_to={'is_staff':True})
    
    email_errors_to_subscribers = models.BooleanField(
        default=True,
        help_text=_('If checked, the stdout and stderr of a job will ' + \
            'be emailed to the subscribers if an error occur.'))
    
    email_success_to_subscribers = models.BooleanField(
        default=False,
        help_text=_('If checked, the stdout of a job will ' + \
            'be emailed to the subscribers if not errors occur.'))
    
    lock_file = models.CharField(
        max_length=255,
        blank=True,
        editable=False)
    
    force_run = models.BooleanField(
        default=False,
        help_text=_("If checked, then this job will be run immediately."))
    
    force_stop = models.BooleanField(
        default=False,
        help_text=_("If checked, and running then this job will be stopped."))
    
    timeout_seconds = models.PositiveIntegerField(
        default=0,
        blank=False,
        null=False,
        help_text=_('''When non-zero, the job will be forcibly killed if running
            for more than this amount of time.'''))
    
    hostname = models.CharField(
        max_length=700,
        blank=True,
        null=True,
        verbose_name='target hostname',
        help_text=_('If given, ensures the job is only run on the server ' + \
            'with the equivalent host name.<br/>Not setting any hostname ' + \
            'will cause the job to be run on the first server that ' + \
            'processes pending jobs.<br/> ' + \
            'e.g. The hostname of this server is <b>%s</b>.') % socket.gethostname())
    
    current_hostname = models.CharField(
        max_length=700,
        blank=True,
        null=True,
        editable=False,
        help_text=_('The name of the host currently running the job.'))
    
    current_pid = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        editable=False,
        db_index=True,
        help_text=_('The ID of the process currently running the job.'))
    
    total_parts_complete = models.PositiveIntegerField(
        default=0,
        editable=False,
        blank=False,
        null=False,
        help_text=_('The total number of parts of the task that are complete.'))
    
    total_parts = models.PositiveIntegerField(
        default=0,
        editable=False,
        blank=False,
        null=False,
        help_text=_('The total number of parts of the task.'))
    
    is_monitor = models.BooleanField(
        default=False,
        help_text=_('If checked, will appear in the monitors section.'))
    
    monitor_url = models.CharField(
        max_length=255, blank=True, null=True,
        help_text=_('URL provided to further explain the monitor.'))
    
    monitor_error_template = models.TextField(
        blank=True, null=True,
        default=const.DEFAULT_MONITOR_ERROR_TEMPLATE,
        help_text=_('If this is a monitor, this is the template used ' + \
            'to compose the error text email.<br/>' + \
            'Available variables: {{ job }} {{ stderr }} {{ url }}'))
    
    monitor_description = models.TextField(
        blank=True, null=True,
        help_text=_('An explanation of the monitor\'s purpose.'))
    
    monitor_records = models.IntegerField(
        blank=True,
        null=True,
        #verbose_name='records',
        editable=False,
        help_text=_('The number of records that need attention.'))
    
    maximum_log_entries = models.PositiveIntegerField(
        default=1000,
        help_text='The maximum number of most recent log entries to keep.' + \
            '<br/>A value of 0 keeps all log entries.')
    
    log_stdout = models.BooleanField(
        default=True,
        help_text=_('''If checked, all characters printed to stdout will be
            saved in a log record.'''))
    
    log_stderr = models.BooleanField(
        default=True,
        help_text=_('''If checked, all characters printed to stderr will be
            saved in a log record.'''))
    
    class Meta:
        ordering = (
            'name',
            #'enabled', 'next_run',
        )
    
    def __unicode__(self):
        if not self.enabled:
            return _(u"%(id)s - %(name)s - disabled") % {'name': self.name, 'id':self.id}
        return u"%i - %s - %s" % (self.id, self.name, self.timeuntil)
    
    @property
    def monitor_url_rendered(self):
        if not self.is_monitor or not self.monitor_url:
            return
        from django.template import Context, Template
        from django.template.loader import render_to_string
        t = Template('{% load chronograph_tags %}' + self.monitor_url)
        c = Context(dict(
            #date=timezone.now(),#.strftime('%Y-%m-%d'),
        ))
        url = t.render(c)
        url = url.replace(' ', '+')
        return url
    
    @property
    def monitor_description_safe(self):
        return mark_safe(self.monitor_description)
    
    @property
    def progress_ratio(self):
        if not self.total_parts_complete and not self.total_parts:
            return
        return self.total_parts_complete/float(self.total_parts)
    
    @property
    def progress_percent(self):
        progress = self.progress_ratio
        if progress is None:
            return
        return min(progress*100, 100)
    
    def progress_percent_str(self):
        progress = self.progress_percent
        if progress is None:
            return ''
        return '%.0f%%' % (progress,)
    progress_percent_str.short_description = 'Progress'
    
    def get_chained_jobs(self):
        """
        Returns a list of jobs that depend on this job.
        Retrieves jobs recursively, stopping if it detects cycles.
        """
        priors = set([self.id])
        pending = list(self.dependents.all().filter(dependent__enabled=True, wait_for_completion=True).values_list('dependent_id', flat=True))
        chained = set()
        while pending:
            job_id = pending.pop(0)
            if job_id in priors:
                continue
            priors.add(job_id)
            job = Job.objects.only('id').get(id=job_id)
            chained.add(job)
            pending.extend(job.dependents.all().filter(dependent__enabled=True, wait_for_completion=True).values_list('dependent_id', flat=True))
        return chained
    
    def get_run_length_estimate(self, samples=20):
        """
        Returns the average run length in seconds.
        """
        q = sorted(list(self.logs.all().values_list('duration_seconds', flat=True).order_by('-run_end_datetime')[:samples]))
        if len(q) >= 3:
            # Drop the upper and lower extremes.
            q = q[1:-1]
        if not q:
            return
        return int(round(sum(q)/float(len(q))))
    
    @property
    def estimated_seconds_to_completion(self):
        """
        Returns an estimate of how many seconds are remaining until processing
        is complete.
        """
        if not self.is_running:
            return
        progress_ratio = self.progress_ratio
        if progress_ratio is None:
            return
        if not self.last_run_start_timestamp:
            return
        td = timezone.now() - self.last_run_start_timestamp
        if not progress_ratio:
            return
        total_sec = td.total_seconds()/progress_ratio
        remaining_sec = total_sec - td.total_seconds()
        return remaining_sec
    
    @property
    def estimated_completion_datetime(self):
        from datetime import datetime, timedelta
        remaining_sec = self.estimated_seconds_to_completion
        if remaining_sec is None:
            return
        return timezone.now() + timedelta(seconds=int(remaining_sec))
    
    def estimated_completion_datetime_str(self):
        c = self.estimated_completion_datetime
        if c is None:
            return ''
        return c.replace(microsecond=0)
    estimated_completion_datetime_str.short_description = 'ETC'
    estimated_completion_datetime_str.help_text = 'Estimated time of completion'
    
    def clean(self, *args, **kwargs):
        cmd1 = (self.command or '').strip()
        cmd2 = (self.raw_command or '').strip()
        if cmd1 and cmd2:
            raise ValidationError({
                'command':[
                    'Either specify command or raw command, but not both.',
                ],
                'raw_command':[
                    'Either specify command or raw command, but not both.',
                ]
            })
        elif not cmd1 and not cmd2:
            raise ValidationError({
                'command':[
                    'Either command or raw command must be specified.',
                ],
                'raw_command':[
                    'Either command or raw command must be specified.',
                ]
            })
        super(Job, self).clean(*args, **kwargs)
    
    def full_clean(self, exclude=None, validate_unique=None, *args, **kwargs):
        return self.clean(*args, **kwargs)
    
    def save(self, *args, **kwargs):
        
        self.full_clean()
        
        if self.enabled:
            if self.pk:
                j = Job.objects.get(pk=self.pk)
            else:
                j = self
            if not self.next_run or j.params != self.params:
                logger.debug("Updating 'next_run")
                next_run = self.next_run or timezone.now()
                
                tz = timezone.get_default_timezone()
                try:
                    self.next_run = self.rrule.after(timezone.make_aware(next_run, tz))
                except ValueError, e:
                    self.next_run = timezone.make_aware(
                        self.rrule.after(timezone.make_naive(next_run, tz)),
                        tz)
                except TypeError, e:
                    self.next_run = timezone.make_aware(
                        self.rrule.after(timezone.make_naive(next_run, tz)),
                        tz)
        
        if not self.is_running:
            self.current_hostname = None
            self.current_pid = None
        
        super(Job, self).save(*args, **kwargs)
        
        # Delete expired logs.
        if self.maximum_log_entries:
            log_q = self.logs.all().order_by('-run_start_datetime')
            for o in log_q[self.maximum_log_entries:]:
                o.delete()

    def dependencies_met(self, running_ids=None):
        """
        Returns true if all dependency scheduling criteria have been met.
        Returns false otherwise.
        """
        for dep in self.dependencies.all():
            if not dep.criteria_met(running_ids=running_ids):
                return False
        return True

    def is_fresh(self):
        lookback_minutes = timedelta(minutes=settings.CHRONIKER_STALE_MINUTES)
        threshold = timezone.now() - lookback_minutes
        return not self.is_running or (
            self.is_running and self.last_heartbeat
            and self.last_heartbeat >= threshold
        )
    is_fresh.boolean = True

    def get_timeuntil(self):
        """
        Returns a string representing the time until the next
        time this Job will be run (actually, the "string" returned
        is really an instance of ``ugettext_lazy``).
        
        >>> job = Job(next_run=timezone.now())
        >>> job.get_timeuntil().translate('en')
        u'due'
        """
        if not self.enabled:
            return _('never (disabled)')
        
        if not self.next_run:
            self.next_run = timezone.now()
        
        delta = self.next_run - timezone.now()
        if delta.days < 0:
            # The job is past due and should be run as soon as possible
            if self.check_is_running():
                return _('running')
            return _('due')
        elif delta.seconds < 60:
            # Adapted from django.utils.timesince
            count = lambda n: ungettext('second', 'seconds', n)
            return ugettext('%(number)d %(type)s') % {'number': delta.seconds,
                                                      'type': count(delta.seconds)}
        return timeuntil(self.next_run)
    get_timeuntil.short_description = _('time until next run')
    timeuntil = property(get_timeuntil)
    
    def get_rrule(self):
        """
        Returns the rrule objects for this ``Job``.  Can also be accessed via the
        ``rrule`` property of the ``Job``.
        
        # Every minute
        >>> last_run = datetime(2011, 8, 4, 7, 19)
        >>> job = Job(frequency="MINUTELY", params="interval:1", last_run=last_run)
        >>> print job.get_rrule().after(last_run)
        2011-08-04 07:20:00
        
        # Every 2 hours
        >>> job = Job(frequency="HOURLY", params="interval:2", last_run=last_run)
        >>> print job.get_rrule().after(last_run)
        2011-08-04 09:19:00
        """
        frequency = eval('rrule.%s' % self.frequency)
        return rrule.rrule(frequency, dtstart=self.next_run, **self.get_params())
    rrule = property(get_rrule)

    def param_to_int(self, param_value):
        """
        Converts a valid rrule parameter to an integer if it is not already one, else
        raises a ``ValueError``.  The following are equivalent:
        
        >>> job = Job(params = "byweekday:1,2,4,5")
        >>> job.get_params()
        {'byweekday': [1, 2, 4, 5]}
        
        >>> job = Job(params = "byweekday:TU,WE,FR,SA")
        >>> job.get_params()
        {'byweekday': [1, 2, 4, 5]}
        """
        if param_value in const.RRULE_WEEKDAY_DICT:
            return const.RRULE_WEEKDAY_DICT[param_value]
        try:
            val = int(param_value)
        except ValueError:
            raise ValueError('rrule parameter should be integer or weekday '
                             'constant (e.g. MO, TU, etc.).  '
                             'Error on: %s' % param_value)
        else:
            return val
    
    def get_params(self):
        """
        Converts a string of parameters into a dict.
        
        >>> job = Job(params = "count:1;bysecond:1;byminute:1,2,4,5")
        >>> job.get_params()
        {'count': 1, 'byminute': [1, 2, 4, 5], 'bysecond': 1}
        """
        if self.params is None:
            return {}
        params = self.params.split(';')
        param_dict = []
        for param in params:
            if param.strip() == "":
                continue # skip blanks
            param = param.split(':')
            if len(param) == 2:
                param = (str(param[0]).strip(), [self.param_to_int(p.strip()) for p in param[1].split(',')])
                if len(param[1]) == 1:
                    param = (param[0], param[1][0])
                param_dict.append(param)
        return dict(param_dict)
    
    def get_args(self):
        """
        Processes the args and returns a tuple or (args, options) for passing
        to ``call_command``.
        
        >>> job = Job(args="arg1 arg2 kwarg1='some value'")
        >>> job.get_args()
        (['arg1', 'arg2', "value'"], {'kwarg1': "'some"})
        """
        args = []
        options = {}
        for arg in self.args.split():
            if arg.find('=') > -1:
                #key, value = arg.split('=')
                parts = arg.split('=')
                key = parts[0]
                value = '='.join(parts[1:])
                options[smart_str(key)] = smart_str(value)
            else:
                args.append(arg)
        return (args, options)
    
    def is_due(self, **kwargs):
        """
        >>> job = Job(next_run=timezone.now())
        >>> job.is_due()
        True
        
        >>> job = Job(next_run=timezone.now()+timedelta(seconds=60))
        >>> job.is_due()
        False
        
        >>> job.force_run = True
        >>> job.is_due()
        True
        
        >>> job = Job(next_run=timezone.now(), enabled=False)
        >>> job.is_due()
        False
        """
        q = type(self).objects.due(job=self, **kwargs)
        return q.exists()
    is_due.boolean = True
    
    def is_due_with_dependencies_met(self, running_ids=None):
        """
        Return true if job is scheduled to run and all dependencies
        are satisified.
        """
        return self.is_due() and self.dependencies_met(running_ids=running_ids)
    
    def run(self, check_running=True, force_run=False, *args, **kwargs):
        """
        Runs this ``Job``.  A ``Log`` will be created if there is any output
        from either stdout or stderr.
        
        Returns ``True`` if the ``Job`` ran, ``False`` otherwise.
        
        The parameter check_running is sometimes given as False when
        the job was just started and we want to do a last minute check for
        dueness and don't want our current run status to give an incorrect
        reading.
        """
        print 'force_run:',force_run
        if force_run:
            self.handle_run(*args, **kwargs)
            return True
        elif self.enabled:
            if not self.dependencies_met():
                # Note, this will cause the job to be re-checked
                # the next time cron runs.
                print 'Job "%s" has unmet dependencies. Aborting run.' % (self.name,)
            elif check_running and self.check_is_running():
                print 'Job "%s" already running. Aborting run.' % (self.name,)
            elif not self.is_due(check_running=check_running):
                print 'Job "%s" not due. Aborting run.' % (self.name,)
            else:
                #call_command('run_job', str(self.pk)) # Calls handle_run().
                self.handle_run(*args, **kwargs)
                return True
        else:
            print 'Job disabled. Aborting run.'
        return False
    
    def handle_run(self, update_heartbeat=True, stdout_queue=None, stderr_queue=None, *args, **kwargs):
        """
        This method implements the code to actually run a ``Job``.  This is
        meant to be run, primarily, by the `run_job` management command as a
        subprocess, which can be invoked by calling this ``Job``\'s ``run``
        method.
        """
        print 'Handling run...'
        
        lock = threading.Lock()
        run_start_datetime = timezone.now()
        last_run_successful = False
        
        original_pid = os.getpid()
        
        try:
            stdout = sys.stdout
            stderr = sys.stderr
            if self.log_stdout:
                stdout = chroniker.utils.TeeFile(
                    sys.stdout,
                    auto_flush=True,
                    queue=stdout_queue)
            if self.log_stderr:
                stderr = chroniker.utils.TeeFile(
                    sys.stderr,
                    auto_flush=True,
                    queue=stderr_queue)
    
            # Redirect output so that we can log it if there is any
            ostdout = sys.stdout
            ostderr = sys.stderr
            sys.stdout = stdout
            sys.stderr = stderr
            
            args, options = self.get_args()
            
            heartbeat = None
            if update_heartbeat:
                heartbeat = JobHeartbeatThread(job_id=self.id, lock=lock)

            try:
                lock.acquire()
#                Job.objects.update()
#                job = Job.objects.get(id=self.id)
#                job.is_running = True
#                job.last_run_start_timestamp = timezone.now()
#                job.current_hostname = socket.gethostname()
#                job.current_pid = str(os.getpid())
#                job.total_parts = 0
#                job.total_parts_complete = 0
#                if heartbeat:
#                    job.lock_file = heartbeat.lock_file.name
#                job.save()
                Job.objects.filter(id=self.id).update(
                    is_running = True,
                    last_run_start_timestamp = timezone.now(),
                    current_hostname = socket.gethostname(),
                    current_pid = str(os.getpid()),
                    total_parts = 0,
                    total_parts_complete = 0,
                    lock_file = heartbeat.lock_file.name if heartbeat and heartbeat.lock_file else '',
                )
            except Exception, e:
                # The command failed to run; log the exception
                t = loader.get_template('chroniker/error_message.txt')
                c = Context({
                  'exception': unicode(e),
                  'traceback': ['\n'.join(traceback.format_exception(*sys.exc_info()))]
                })
                print>>sys.stderr, t.render(c)
                success = False
            finally:
                lock.release()
            
            if heartbeat:
                heartbeat.start()
            success = True
            try:
                logger.debug("Calling command '%s'" % self.command)
                if self.raw_command:
                    retcode = subprocess.call(
                        self.raw_command,
                        shell=True,
                        stdout=sys.stdout,
                        stderr=sys.stderr)
                else:
                    call_command(self.command, *args, **options)
                logger.debug("Command '%s' completed" % self.command)
                if original_pid != os.getpid():
                    return
            except Exception, e:
                if original_pid != os.getpid():
                    return
                # The command failed to run; log the exception
                t = loader.get_template('chroniker/error_message.txt')
                c = Context({
                  'exception': unicode(e),
                  'traceback': ['\n'.join(traceback.format_exception(*sys.exc_info()))]
                })
                print>>sys.stderr, t.render(c)
                success = False
            
            # Stop the heartbeat
            if heartbeat:
                logger.debug("Stopping heartbeat")
                heartbeat.stop()
                heartbeat.join()
            
            # If this was a forced run, then don't update the
            # next_run date.
            #next_run = self.next_run.replace(tzinfo=None)
            next_run = self.next_run
            if not self.force_run:
                print "Determining 'next_run' for job %d..." % (self.id,)
                if next_run < timezone.now():
                    next_run = timezone.now()
                _next_run = next_run
                next_run = self.rrule.after(next_run)
                print _next_run, next_run
                assert next_run != _next_run, \
                    'RRule failed to increment next run datetime.'
            #next_run = next_run.replace(tzinfo=timezone.get_current_timezone()) 
            
            last_run_successful = not bool(stderr.length)
            
            try:
                lock.acquire()
                Job.objects.update()
#                job = Job.objects.get(id=self.id)
#                job.is_running = False
#                job.lock_file = ""
#                job.last_run = run_start_datetime
#                job.force_run = False
#                job.next_run = next_run
#                job.last_run_successful = last_run_successful
#                # Ensure we report 100% progress if everything ran successfully.
#                if job.last_run_successful and job.total_parts is not None:
#                    job.total_parts_complete = job.total_parts
#                job.save()
                job = Job.objects.only('id', 'total_parts', 'last_run_successful').get(id=self.id)
                Job.objects.filter(id=self.id).update(
                    is_running = False,
                    lock_file = '',
                    last_run = run_start_datetime,
                    force_run = False,
                    next_run = next_run,
                    last_run_successful = last_run_successful,
                    total_parts_complete = (job.last_run_successful and job.total_parts) or 0,
                )
            except Exception, e:
                # The command failed to run; log the exception
                t = loader.get_template('chroniker/error_message.txt')
                c = Context({
                  'exception': unicode(e),
                  'traceback': ['\n'.join(traceback.format_exception(*sys.exc_info()))]
                })
                print>>sys.stderr, t.render(c)
                success = False
            finally:
                lock.release()
                            
        finally:
            
            if original_pid != os.getpid():
                # We're a clone of the parent job, so exit immediately
                # so we don't conflict.
                return
            
            # Redirect output back to default
            sys.stdout = ostdout
            sys.stderr = ostderr
            
            # Record run log.
            print 'Recording log...'
            
            stdout_str = ''
            if self.log_stdout:
                stdout_str = stdout.getvalue()
                if isinstance(stdout_str, unicode):
                    stdout_str = stdout_str.encode('utf-8', 'replace')
                else:
                    stdout_str = unicode(stdout_str, 'utf-8', 'replace')
            
            stderr_str = ''
            if self.log_stderr:
                stderr_str = stderr.getvalue()
                if isinstance(stderr_str, unicode):
                    stderr_str = stderr_str.encode('utf-8', 'replace')
                else:
                    stderr_str = unicode(stderr_str, 'utf-8', 'replace')
            
            run_end_datetime = timezone.now()
            duration_seconds = (run_end_datetime - run_start_datetime).total_seconds()
            log = Log.objects.create(
                job = self,
                run_start_datetime = run_start_datetime,
                run_end_datetime = run_end_datetime,
                duration_seconds = duration_seconds,
                hostname=socket.gethostname(),
                stdout = stdout_str,
                stderr = stderr_str,
                success = last_run_successful,
            )
            
            # Email subscribers.
            try:
                if last_run_successful:
                    if self.email_success_to_subscribers:
                        log.email_subscribers()
                else:
                    if self.email_errors_to_subscribers:
                        log.email_subscribers()
            except Exception, e:
                print>>sys.stderr, e
            
            # If an exception occurs above, ensure we unmark is_running.
            lock.acquire()
            Job.objects.update()
            job = Job.objects.get(id=self.id)
            if job.is_running:
                # This should only be reached if an error ocurred above.
                job.is_running = False
                job.last_run_successful = False
                job.save()
            lock.release()
            
            print 'Job done.'
    
    def check_is_running(self):
        """
        This function actually checks to ensure that a job is running.
        Currently, it only supports `posix` systems.  On non-posix systems
        it returns the value of this job's ``is_running`` field.
        """
        if settings.CHRONIKER_CHECK_LOCK_FILE \
        and self.is_running and self.lock_file:
            # The Job thinks that it is running, so lets actually check
            # NOTE: This will screw up the record if separate hosts
            # are processing and reading the jobs.
            if os.path.exists(self.lock_file):
                # The lock file exists, but if the file hasn't been modified
                # in less than LOCK_TIMEOUT seconds ago, we assume the process
                # is dead.
                if (time.time() - os.stat(self.lock_file).st_mtime) \
                <= settings.CHRONIKER_LOCK_TIMEOUT:
                    return True
            
            # This job isn't running; update it's info
            self.is_running = False
            self.lock_file = ""
            self.save()
            return False
        else:
            # We assume the database record is definitive.
            return self.is_running
    check_is_running.short_description = "is running"
    check_is_running.boolean = True
    
    @classmethod
    def update_progress(cls, *args, **kwargs):
        heartbeat = get_current_heartbeat()
        if heartbeat:
            return heartbeat.update_progress(*args, **kwargs)
        else:
            #print 'Unable to update progress. No heartbeat found.'
            pass

class Log(models.Model):
    """
    A record of stdout and stderr of a ``Job``.
    """
    
    job = models.ForeignKey(Job, related_name='logs')
    
    run_start_datetime = models.DateTimeField(
        editable=False,
        db_index=True,
        default=timezone.now,
        blank=False,
        null=False)
    
    run_end_datetime = models.DateTimeField(
        editable=False,
        db_index=True,
        blank=True,
        null=True)
    
    duration_seconds = models.PositiveIntegerField(
        editable=False,
        db_index=True,
        verbose_name='duration (total seconds)',
        blank=True,
        null=True)
    
    stdout = models.TextField(blank=True)
    
    stderr = models.TextField(blank=True)
    
    hostname = models.CharField(
        max_length=700,
        blank=True,
        null=True,
        editable=False,
        help_text=_('The hostname this job was executed on.'))
    
    success = models.BooleanField(
        default=True,
        db_index=True,
        editable=False)
        
    on_time = models.BooleanField(
        default=True,
        db_index=True,
        editable=False,
        help_text=_('''If true, indicates job completed of its own accord.
            If false, the job exceeded a timeout threshold and was forcibly
            killed.'''))
    
    class Meta:
        ordering = ('-run_start_datetime',)
    
    def __unicode__(self):
        return u"%s - %s" % (self.job.name, self.run_start_datetime)
    
    def save(self, *args, **kwargs):
        if self.run_start_datetime and self.run_end_datetime:
            assert self.run_start_datetime <= self.run_end_datetime, 'Job must start before it ends.'
            time_diff = (self.run_end_datetime - self.run_start_datetime)
            self.duration_seconds = time_diff.total_seconds()
        super(Log, self).save(*args, **kwargs)
    
    def duration_str(self):
        from datetime import datetime, timedelta
        sec = timedelta(seconds=self.duration_seconds)
        d = datetime(1,1,1) + sec
        days = d.day-1
        hours = d.hour
        minutes = d.minute
        seconds = d.second
        return '%02i:%02i:%02i:%02i' % (days, hours, minutes, seconds)
    duration_str.short_description = 'duration (days:hours:min:sec)'
    duration_str.allow_tags = True
    
    def email_subscribers(self):
        current_site = Site.objects.get_current()
        
        subscribers = []
        for user in self.job.subscribers.all():
            subscribers.append('"%s" <%s>' % \
                (user.get_full_name(), user.email))
        
        is_error = bool((self.stderr or '').strip())
        if is_error:
            subject_tmpl = settings.CHRONIKER_EMAIL_SUBJECT_ERROR
        else:
            subject_tmpl = settings.CHRONIKER_EMAIL_SUBJECT_SUCCESS
        
        args = self.__dict__.copy()
        args['job'] = self.job
        args['stderr'] = self.stderr if self.job.is_monitor else None
        args['url'] = mark_safe('http://%s%s' % \
            (current_site.domain, self.job.monitor_url_rendered))
        c = Context(args)
        subject = Template(subject_tmpl).render(c)
        
        if is_error and self.job.is_monitor \
        and self.job.monitor_error_template:
            body = Template(self.job.monitor_error_template).render(c)
        else:
            body = "Ouput:\n%s\nError output:\n%s" % (self.stdout, self.stderr)
        
        #site = get_current_site()
        site = Site.objects.get_current()
        base_url = None
        if hasattr(settings, 'BASE_SECURE_URL'):
            base_url = settings.BASE_SECURE_URL
        elif hasattr(settings, 'BASE_URL'):
            base_url = settings.BASE_URL
        elif site:
            if domain.startswith('http'):
                base_url = site.domain
            else:
                base_url = 'http://' + site.domain
        
        if base_url:
            admin_link = settings.BASE_SECURE_URL + chroniker.utils.get_admin_change_url(self.job)
            body = 'To manage this job please visit: ' + admin_link + '\n\n' + body
        
        send_mail(
            from_email = '"%s" <%s>' % (
                settings.CHRONIKER_EMAIL_SENDER,
                settings.CHRONIKER_EMAIL_HOST_USER),
            subject = subject,
            recipient_list = subscribers,
            message = body
        )
    
    def stdout_sample(self):
        result = self.stdout or ''
        if len(result) > 40:
            result = result[:40] + '...'
        return result or '(No output)'

    def stderr_sample(self):
        result = self.stderr or ''
        if len(result) > 40:
            result = result[:40] + '...'
        return result or '(No errors)'
    
    def stdout_long_sample(self):
        l = 10000
        result = self.stdout or ''
        if len(result) > l*3:
            result = result[:l] + '\n...\n' + result[-l:]
        result = result.replace('\n', '<br/>')
        return result or '(No output)'
    stdout_long_sample.allow_tags = True

    def stderr_long_sample(self):
        l = 10000
        result = self.stderr or ''
        if len(result) > l*3:
            result = result[:l] + '\n...\n' + result[-l:]
        result = result.replace('\n', '<br/>')
        return result or '(No output)'
    stderr_long_sample.allow_tags = True
    
    @classmethod
    def cleanup(cls, time_ago=None):
        """
        Deletes all log entries older than the given date.
        """
        q = cls.objects.all()
        if time_ago:
            q = q.filter(run_start_datetime__lte = time_ago)
        q.delete()

class MonitorManager(models.Manager):
    
    def all(self):
        q = super(MonitorManager, self).all()
        q = q.filter(is_monitor=True)
        return q

class Monitor(Job):
    
    objects = MonitorManager()
    
    class Meta:
        proxy = True
