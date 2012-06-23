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
import thread

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.management import call_command
from django.db import models, connection
from django.db.models import Q
from django.template import loader, Context, Template
from django.utils.encoding import smart_str
from django.utils.timesince import timeuntil
from django.utils.translation import ungettext, ugettext, ugettext_lazy as _

import chroniker.settings
import chroniker.utils

logger = logging.getLogger('chroniker.models')

RRULE_WEEKDAY_DICT = {"MO":0,"TU":1,"WE":2,"TH":3,"FR":4,"SA":5,"SU":6}

class JobManager(models.Manager):
    
    def due(self):
        """
        Returns a ``QuerySet`` of all jobs waiting to be run.  NOTE: this may
        return ``Job``s that are still currently running; it is your
        responsibility to call ``Job.check_is_running()`` to determine whether
        or not the ``Job`` actually needs to be run.
        """
        q = self.select_for_update()
        q = self.filter(Q(next_run__lte=datetime.now()) | Q(force_run=True))
        q = self.filter(
            Q(hostname__isnull=True) | Q(hostname=socket.gethostname()))
        q = q.filter(enabled=True)
        return q

    def stale(self):
        q = self.filter(is_running=True)
        q = q.filter(
            Q(last_heartbeat__isnull=True) | 
            Q(last_heartbeat__lt=datetime.now() - timedelta(minutes=5)))
        return q
    
# A lot of rrule stuff is from django-schedule
freqs = (   ("YEARLY", _("Yearly")),
            ("MONTHLY", _("Monthly")),
            ("WEEKLY", _("Weekly")),
            ("DAILY", _("Daily")),
            ("HOURLY", _("Hourly")),
            ("MINUTELY", _("Minutely")),
            ("SECONDLY", _("Secondly")))

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
        threading.Thread.__init__(self, *args, **kwargs)

    def run(self):
        """
        Do not call this directly; call ``start()`` instead.
        """
        while not self.halt:
            #print 'Heartbeat check...'
            self.lock_file.seek(0)
            self.lock_file.write(str(time.time()))
            self.lock_file.flush()
            
            # Check job status and save heartbeat timestamp.
            self.lock.acquire()
            Job.objects.update()
            job = Job.objects.get(id=self.job_id)
            job.last_heartbeat = datetime.now()
            force_stop = job.force_stop
            job.force_stop = False
            job.force_run = False
            job.save()
            self.lock.release()
            
            # If we noticed we're being forced to stop, then interrupt main.
            if force_stop:
                self.halt = True
                thread.interrupt_main()
                return
            
            time.sleep(10)
    
    def stop(self):
        """
        Call this to stop the heartbeat.
        """
        self.halt = True
        while self.is_alive():
            #print 'Waiting for heartbeat to stop...'
            time.sleep(.1)
        self.lock_file.close()

class JobDependency(models.Model):
    """
    Represents a scheduling dependency between two jobs.
    """
    
    dependent = models.ForeignKey('Job', related_name='dependencies')
    
    dependee = models.ForeignKey('Job', related_name='dependents')
    
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
    
    def criteria_met(self):
        if self.wait_for_completion and self.dependee.is_running:
            # Don't run until our dependency completes.
            return False
        if self.wait_for_success and not self.dependee.last_run_successful:
            # Don't run until our dependency completes successfully.
            return False
        if self.wait_for_next_run:
            # Don't run until our dependency is scheduled until after
            # our next run.
            if not self.dependent.next_run or not self.dependee.next_run:
                return False
            if self.dependee.next_run < self.dependent.next_run:
                return False
        return True
    criteria_met.boolean = True
    
    class Meta:
        
        unique_together = (
            ('dependent', 'dependee'),
        )

class Job(models.Model):
    """
    A recurring ``django-admin`` command to be run.
    """
    name = models.CharField(
        _("name"),
        max_length=200)
    
    frequency = models.CharField(
        _("frequency"),
        choices=freqs,
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
    
    enabled = models.BooleanField(
        default=True,
        help_text=_('If checked this job will run.'))
    
    next_run = models.DateTimeField(
        _("next run"),
        blank=True,
        null=True,
        help_text=_("If you don't set this it will"
            " be determined automatically"))
    
    last_run = models.DateTimeField(
        _("last run"),
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
        editable=False)
    
    last_run_successful = models.NullBooleanField(
        _('success'),
        blank=True,
        null=True,
        editable=False)
    
    subscribers = models.ManyToManyField(
        User,
        blank=True,
        limit_choices_to={'is_staff':True})
    
    email_errors_to_subscribers = models.BooleanField(
        default=True,
        help_text='If checked, the stdout and stderr of a job will ' + \
            'be emailed to the subscribers if an error occur.')
    
    email_success_to_subscribers = models.BooleanField(
        default=False,
        help_text='If checked, the stdout of a job will ' + \
            'be emailed to the subscribers if not errors occur.')
    
    lock_file = models.CharField(
        max_length=255,
        blank=True,
        editable=False)
    
    force_run = models.BooleanField(
        default=False,
        help_text=_("If checked then this job will be run immediately."))
    
    force_stop = models.BooleanField(
        default=False,
        help_text=_("If checked and running then this job will be stopped."))
    
    hostname = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=('If given, ensures the job is only run on the server ' + \
            'with the equivalent host name.<br/>Not setting any hostname ' + \
            'will cause the job to be ran on an arbitrary server.<br/> ' + \
            'The current hostname is <b>%s</b>.') % socket.gethostname())
    
    objects = JobManager()
    
    class Meta:
        ordering = (
            'name',
            #'enabled', 'next_run',
        )
    
    def __unicode__(self):
        if not self.enabled:
            return _(u"%(name)s - disabled") % {'name': self.name}
        return u"%s - %s" % (self.name, self.timeuntil)
    
    def save(self, *args, **kwargs):
        if not self.enabled:
            self.next_run = None
        else:
            if self.pk:
                j = Job.objects.get(pk=self.pk)
            else:
                j = self
            if not self.next_run or j.params != self.params:
                logger.debug("Updating 'next_run")
                next_run = self.next_run or datetime.now()
                self.next_run = self.rrule.after(next_run)
        
        super(Job, self).save(*args, **kwargs)

    def dependencies_met(self):
        """
        Returns true if all dependency scheduling criteria have been met.
        Returns false otherwise.
        """
        for dep in self.dependencies.all():
            if not dep.criteria_met():
                return False
        return True

    def is_fresh(self):
        return not self.is_running or (
            self.is_running and self.last_heartbeat
            and self.last_heartbeat >= datetime.now() - timedelta(minutes=5)
        )
    is_fresh.boolean = True

    def get_timeuntil(self):
        """
        Returns a string representing the time until the next
        time this Job will be run (actually, the "string" returned
        is really an instance of ``ugettext_lazy``).
        
        >>> job = Job(next_run=datetime.now())
        >>> job.get_timeuntil().translate('en')
        u'due'
        """
        if not self.enabled:
            return _('never (disabled)')
        
        delta = self.next_run - datetime.now()
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
        return rrule.rrule(frequency, dtstart=self.last_run, **self.get_params())
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
        if param_value in RRULE_WEEKDAY_DICT:
            return RRULE_WEEKDAY_DICT[param_value]
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
                key, value = arg.split('=')
                options[smart_str(key)] = smart_str(value)
            else:
                args.append(arg)
        return (args, options)
    
    def is_due(self):
        """
        >>> job = Job(next_run=datetime.now())
        >>> job.is_due()
        True
        
        >>> job = Job(next_run=datetime.now()+timedelta(seconds=60))
        >>> job.is_due()
        False
        
        >>> job.force_run = True
        >>> job.is_due()
        True
        
        >>> job = Job(next_run=datetime.now(), enabled=False)
        >>> job.is_due()
        False
        """
        reqs =  (
            self.next_run <= datetime.now()
            and self.enabled
            and self.check_is_running() == False
        )
        return (reqs or self.force_run)
    
    def run(self):
        """
        Runs this ``Job``.  A ``Log`` will be created if there is any output
        from either stdout or stderr.
        
        Returns ``True`` if the ``Job`` ran, ``False`` otherwise.
        """
        if self.enabled:
            if not self.dependencies_met():
                # Note, this will cause the job to be re-checked
                # the next time cron runs.
                print 'Job has unmet dependencies. Aborting run.'
            if self.check_is_running():
                print 'Job already running. Aborting run.'
            elif not self.is_due():
                print 'Job not due. Aborting run.'
            else:
                call_command('run_job', str(self.pk)) # Calls handle_run().
                return True
        else:
            print 'Job disabled. Aborting run.'
        return False
    
    def handle_run(self):
        """
        This method implements the code to actually run a ``Job``.  This is
        meant to be run, primarily, by the `run_job` management command as a
        subprocess, which can be invoked by calling this ``Job``\'s ``run``
        method.
        """
        
        lock = threading.Lock()
        run_start_datetime = datetime.now()
        last_run_successful = False
        stdout = chroniker.utils.TeeFile(sys.stdout, auto_flush=True)
        stderr = chroniker.utils.TeeFile(sys.stderr, auto_flush=True)
        
        try:
    
            # Redirect output so that we can log it if there is any
            ostdout = sys.stdout
            ostderr = sys.stderr
            sys.stdout = stdout
            sys.stderr = stderr
            
            args, options = self.get_args()
    
            heartbeat = JobHeartbeatThread(job_id=self.id, lock=lock)
            
            lock.acquire()
            Job.objects.update()
            job = Job.objects.get(id=self.id)
            job.is_running = True
            job.lock_file = heartbeat.lock_file.name
            job.save()
            lock.release()
            
            t0 = time.time()
            heartbeat.start()
            success = True
            try:
                logger.debug("Calling command '%s'" % self.command)
                call_command(self.command, *args, **options)
                logger.debug("Command '%s' completed" % self.command)
            except Exception, e:
                # The command failed to run; log the exception
                t = loader.get_template('chroniker/error_message.txt')
                c = Context({
                  'exception': unicode(e),
                  'traceback': ['\n'.join(traceback.format_exception(*sys.exc_info()))]
                })
                print>>sys.stderr, t.render(c)
                success = False
            
            # Stop the heartbeat
            logger.debug("Stopping heartbeat")
            heartbeat.stop()
            heartbeat.join()
            
            # If this was a forced run, then don't update the
            # next_run date
            next_run = self.next_run
            if not self.force_run:
                #print "Determining 'next_run'"
                while next_run < datetime.now():
                    _next_run = next_run
                    next_run = self.rrule.after(next_run)
                    #print "'next_run = ' %s" % next_run
                    assert next_run != _next_run, \
                        'RRule failed to increment next run datetime.'
            
            last_run_successful = not bool(stderr.length)
                
            lock.acquire()
            Job.objects.update()
            job = Job.objects.get(id=self.id)
            job.is_running = False
            job.lock_file = ""
            job.last_run = datetime(
                run_start_datetime.year,
                run_start_datetime.month,
                run_start_datetime.day,
                run_start_datetime.hour,
                run_start_datetime.minute)
            job.force_run = False
            job.next_run = next_run
            job.last_run_successful = last_run_successful
            job.save()
            lock.release()
            
        finally:
            
            # Redirect output back to default
            sys.stdout = ostdout
            sys.stderr = ostderr
            
            # Record run log.
            print 'Recording log...'
            log = Log.objects.create(
                job = self,
                run_start_datetime = run_start_datetime,
                run_end_datetime = datetime.now(),
                duration_seconds = time.time() - t0,
                stdout = stdout.getvalue(),
                stderr = stderr.getvalue(),
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
        if self.is_running and self.lock_file:
            # The Job thinks that it is running, so lets actually check
            if os.path.exists(self.lock_file):
                # The lock file exists, but if the file hasn't been modified
                # in less than LOCK_TIMEOUT seconds ago, we assume the process
                # is dead
                if (time.time() - os.stat(self.lock_file).st_mtime) <= chroniker.settings.LOCK_TIMEOUT:
                    return True
            
            # This job isn't running; update it's info
            self.is_running = False
            self.lock_file = ""
            self.save()
        return False
    check_is_running.short_description = "is running"
    check_is_running.boolean = True

class Log(models.Model):
    """
    A record of stdout and stderr of a ``Job``.
    """
    job = models.ForeignKey(Job, related_name='logs')
    run_start_datetime = models.DateTimeField(
        editable=False,
        default=datetime.now,
        blank=False,
        null=False)
    run_end_datetime = models.DateTimeField(
        editable=False,
        blank=True,
        null=True)
    duration_seconds = models.PositiveIntegerField(
        editable=False,
        blank=True,
        null=True)
    stdout = models.TextField(blank=True)
    stderr = models.TextField(blank=True)
    success = models.BooleanField(default=True, editable=False)
        
    class Meta:
        ordering = ('-run_start_datetime',)
    
    def __unicode__(self):
        return u"%s - %s" % (self.job.name, self.run_start_datetime)
    
    def email_subscribers(self):
        subscribers = []
        for user in self.job.subscribers.all():
            subscribers.append('"%s" <%s>' % (user.get_full_name(), user.email))
        
        is_error = bool((self.stderr or '').strip())
        if is_error:
            subject_tmpl = chroniker.settings.EMAIL_SUBJECT_ERROR
        else:
            subject_tmpl = chroniker.settings.EMAIL_SUBJECT_SUCCESS
        
        t = Template(subject_tmpl)
        args = self.__dict__.copy()
        args['job'] = self.job
        c = Context(args)
        subject = t.render(c)
        
        send_mail(
            from_email = '"%s" <%s>' % (
                chroniker.settings.EMAIL_SENDER,
                chroniker.settings.EMAIL_HOST_USER),
            subject = subject,
            recipient_list = subscribers,
            message = "Ouput:\n%s\nError output:\n%s" % (self.stdout, self.stderr)
        )
        