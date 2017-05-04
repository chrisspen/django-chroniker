"""
Quick run with:

    export TESTNAME=.testJobRawCommand; tox -e py27-django17

"""
from __future__ import print_function

import os
import sys
import datetime
from datetime import timedelta
import time
import socket
import warnings
from multiprocessing import Process

import pytz

import six
try:
    from io import StringIO
    from io import BytesIO
except ImportError:
    from cStringIO import StringIO
    from cStringIO import StringIO as BytesIO

import django
from django.core.management import call_command
from django.core import mail
from django.test import TestCase
from django.test.client import Client
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models import Max

from chroniker.models import Job, Log
# from chroniker.tests.commands import Sleeper, InfiniteWaiter, ErrorThrower
# from chroniker.management.commands.cron import run_cron
from chroniker import utils
from chroniker import constants as c

warnings.simplefilter('error', RuntimeWarning)

socket.gethostname = lambda: 'localhost'

CALLBACK_ERRORS = []

def job_error_callback(job, stdout, stderr):
    print('Error for job %s' % job)
    print(stderr, file=sys.stderr)
    CALLBACK_ERRORS.append(stderr)

class JobProcess(Process):

    def run(self):
        print('Job process started.')
        while 1:
            print('Job process waiting (pid=%i)...' % (os.getpid(),))
            time.sleep(1)
        print('Job process stopped.')

class JobTestCase(TestCase):

    fixtures = ['test_jobs.json']

    def setUp(self):
        pass

    def testJobRun(self):
        """
        Test that the jobs run properly.
        """
        self.assertEqual(Job.objects.filter(enabled=True).count(), 5)

        for job in Job.objects.due():
            try:
                time_expected = float(job.args)
            except ValueError:
                continue

            time_start = time.time()
            #TODO:heartbeat thread can't access sqlite3 models?
            #Throws "DatabaseError: no such table: chroniker_job".
            #Causes django-admin.py to consume 100% cpu?
            job.run(update_heartbeat=0)
            time_end = time.time()

            time_taken = time_end - time_start
            self.assertTrue(time_taken >= time_expected)

    def testCronCommand(self):
        """
        Test that the ``cron`` command runs all jobs in parallel.
        """

        # Pick the longest running Job
        job = sorted(
            Job.objects.due().filter(command="test_sleeper"),
            key=lambda j: -int(j.args))[0]

        # The "args" property simply describes the number of seconds the Job
        # should take to run
        time_expected = float(job.args)

        time_start = time.time()
        #call_command('cron', update_heartbeat=0)
        call_command('run_job', job.id, update_heartbeat=0)
        time_end = time.time()

        time_taken = time_end - time_start
        self.assertTrue(time_taken >= time_expected)

    def testCronCleanCommand(self):
        """
        Test that the ``cron_clean`` command runs properly.
        """
        # Pick the shortest running Job
        job = sorted(
            Job.objects.due().filter(command="test_sleeper"),
            key=lambda j: int(j.args))[0]

        # Run the job 5 times
        for i in range(5):
            job.run(update_heartbeat=0)

        # Ensure that we have 5 Log objects
        self.assertEqual(Log.objects.count(), 1)

        # Ensure we can convert a log instances to unicode.
        s = six.text_type(Log.objects.all()[0])
        self.assertTrue(s.startswith('Sleep '), s)

        # Now clean out the logs that are older than 0 minutes (all of them)
        #call_command('cron_clean', 'minutes', '0')
        Log.cleanup()

        # Ensure that we have 0 Log objects
        self.assertEqual(Log.objects.count(), 0)

    def testDependencies(self):
        """
        Confirm inter-job dependencies are detected.

        2 dependent on 1
        2 dependent on 3
        3 dependent on 4
        """

        # 1 comes before 2
        # 3 comes before 2
        # 4 comes before 3
        j1 = Job.objects.get(id=1)
        j2 = Job.objects.get(id=2)# needs j1 and j3
        self.assertEqual(j2.dependencies.all().count(), 2)
        j3 = Job.objects.get(id=3)# need j4
        self.assertEqual(j3.dependencies.all().count(), 1)
        j4 = Job.objects.get(id=4)
        j5 = Job.objects.get(id=5)
        j6 = Job.objects.get(id=6)

        self.assertEqual(j1.is_due(), True)
        self.assertEqual(j2.is_due(), True)
        self.assertEqual(j3.is_due(), True)
        self.assertEqual(j4.is_due(), True)
        self.assertEqual(j5.is_due(), False)

        self.assertEqual(
            set(_.dependent for _ in j1.dependents.all()),
            set([j2]))
        self.assertEqual(
            j1.dependents.filter(dependent=j2).count(),
            1)

        self.assertEqual(
            set(_.dependee for _ in j1.dependencies.all()),
            set([]))

        self.assertEqual(
            set(_.dependent for _ in j2.dependents.all()),
            set([]))

        self.assertEqual(
            set(_.dependee for _ in j2.dependencies.all()),
            set([j1, j3]))
        self.assertEqual(j2.dependencies.filter(dependee=j1).count(), 1)
        self.assertEqual(j2.dependencies.filter(dependee=j3).count(), 1)

        jobs = Job.objects.ordered_by_dependencies(Job.objects.filter(enabled=True))
#        for job in jobs:
#            print(job, [_.dependee for _ in job.dependencies.all()])
        print('jobs1:', [_.id for _ in jobs])

        # 1 comes before 2
        self.assertTrue(jobs.index(j1) < jobs.index(j2))

        # 3 comes before 2
        self.assertTrue(jobs.index(j3) < jobs.index(j2))

        # 4 comes before 3
        self.assertTrue(jobs.index(j4) < jobs.index(j3))

        # Ensure all dependent jobs come after their dependee job.
        due = Job.objects.due_with_met_dependencies_ordered()
        print('dueA:', [_.id for _ in due])

        # 1 comes before 2
        self.assertTrue(due.index(j1) < jobs.index(j2))

        # 3 comes before 2
        self.assertTrue(due.index(j3) < jobs.index(j2))

        # 4 comes before 3
        self.assertTrue(due.index(j4) < jobs.index(j3))

        # Note, possible bug? call_command() causes all models
        # changes made within the command to be lost.
        # e.g. Even though it appears to correctly run the job,
        # querying the job's next_run date will show the old original date.
        # As a workaround for testing, we just run them all directly.
        #call_command('cron', update_heartbeat=0)
        for job in due:
            job.run(update_heartbeat=0)

        # Everything just ran, and they shouldn't run again for an hour, so we should
        # find nothing due.
        Job.objects.update(is_running=False, last_heartbeat=timezone.now())
        Job.objects.update()
        due = list(Job.objects.due_with_met_dependencies())
        print('dueB:', due)
        self.assertEqual(
            due,
            [
                #Job.objects.get(args="5"),
            ])

        for job in due:
            job.run(update_heartbeat=0)

        Job.objects.update()
        due = list(Job.objects.due_with_met_dependencies())
        print('dueC:', due)
        self.assertEqual(
            due,
            [
                #Job.objects.get(args="2"),
            ])

    def testStaleCleanup(self):
        """
        Confirm that stale jobs are correctly resolved.
        """
        job = Job.objects.get(id=1)

        # Simulate a running job having crashed, leaving itself marked
        # as running with no further updates.
        job.is_running = True
        job.last_heartbeat = timezone.now() - datetime.timedelta(days=60)
        job.save()
        self.assertEqual(job.is_running, True)
        self.assertEqual(job.is_fresh(), False)
        self.assertEqual(job.is_stale(), True)

        Job.objects.end_all_stale()

        job = Job.objects.get(id=1)
        self.assertEqual(job.is_running, False)
        self.assertEqual(job.last_run_successful, False)
        self.assertEqual(job.is_fresh(), True)
        self.assertEqual(job.is_stale(), False)

        # TODO:Ideally this would use run_cron(),
        # but attempting to access Django models inside a thread/process
        # when inside a unittest currently throw "no such table" errors because
        # they're not using the in-memory sqlite db...
        job = Job.objects.get(id=5)
        job.enabled = True
        job.is_running = True
        job.last_heartbeat = timezone.now() - timedelta(days=30)
        job.save()

        self.assertEqual(job.is_fresh(), False)

        # Simulate the job's stalled running process.
        proc = JobProcess()
        proc.daemon = True
        proc.start()

        # Wait for process to start.
        while not proc.is_alive():
            time.sleep()

        self.assertTrue(proc.pid)
        job.current_hostname = socket.gethostname()
        job.current_pid = proc.pid
        job.save()
        self.assertEqual(job.is_fresh(), False)

        Job.objects.end_all_stale()

        while 1:
            proc.terminate()
            time.sleep(1)
            if not proc.is_alive():
                break

    def testJobRawCommand(self):

        job = Job.objects.create(
            name='raw command test',
            frequency=c.MINUTELY,
            raw_command='echo "hello"',
            enabled=True,
            force_run=True,
        )
        self.assertEqual(job.logs.all().count(), 0)
        job.run(update_heartbeat=0)
        self.assertEqual(job.logs.all().count(), 1)

        stdout_str = Log.objects.get(id=1).stdout
        self.assertEqual(stdout_str, 'hello\n')
        stderr_str = Log.objects.get(id=1).stderr
        self.assertEqual(stderr_str, '')

        # Disable logging.
        Job.objects.update()
        job = Job.objects.get(id=job.id)
        job.log_stdout = False
        job.log_stderr = False
        job.force_run = True
        job.save()

        # Re-run.
        self.assertEqual(job.logs.all().count(), 1)
        job.run(update_heartbeat=0)
        self.assertEqual(job.logs.all().count(), 2)

        # Confirm nothing was logged.
        stdout_str = Log.objects.get(id=2).stdout
        self.assertEqual(stdout_str, '')
        stderr_str = Log.objects.get(id=2).stderr
        self.assertEqual(stderr_str, '')

    def testTimezone(self):

        self.assertEqual(settings.USE_TZ, True)
        j = Job()
        j.command = "test_sleeper"
        j.frequency = "MINUTELY"
        j.enabled = True
        j.params = "interval:10"
        j.next_run = datetime.datetime(2014, 6, 27, 14, 31, 4)
        j.save()

        # Test someone turning-on timezone awareness after job was created.
        try:
            settings.USE_TZ = False
            j = Job()
            j.command = "test_sleeper"
            j.frequency = "MINUTELY"
            j.enabled = True
            j.save()
            self.assertTrue(j.next_run)
            settings.USE_TZ = True
            j.params = "interval:10"
            j.next_run = datetime.datetime(2014, 6, 27, 14, 31, 4)
            j.save()
        finally:
            settings.USE_TZ = True

    def testTimezone2(self):
        from dateutil import zoneinfo
        tz = zoneinfo.gettz(settings.TIME_ZONE)
        _USE_TZ = settings.USE_TZ
        settings.USE_TZ = False
        try:
            self.assertEqual(settings.USE_TZ, False)

            username = 'joe'
            password = 'password'
            user = User.objects.create(
                username=username,
                email='joe@joe.com',
                is_active=True,
                is_staff=True,
                is_superuser=True,
            )
            user.set_password(password)
            user.save()

            client = Client()
            ret = client.login(username=username, password=password)
            self.assertTrue(ret)

            j = Job.objects.get(id=1)
            next_run = j.next_run
            print('next_run:', next_run)
            self.assertTrue(timezone.is_naive(next_run))
            with self.assertRaises(ValueError):
                #astimezone() cannot be applied to a naive datetime
                timezone.make_naive(j.next_run, timezone=tz)
            j.save()

            response = client.get('/admin/chroniker/job/')
            self.assertEqual(response.status_code, 200)

        finally:
            settings.USE_TZ = _USE_TZ

    def testWriteLock(self):
        import tempfile
        lock_file = tempfile.NamedTemporaryFile()
        utils.write_lock(lock_file)
        lock_file.close()

    def testNaturalKey(self):
        if django.VERSION[:3] <= (1, 5, 0):
            #TODO: support other versions once admin-steroids updated

            Job.objects.all().delete()

            settings.CHRONIKER_JOB_NK = ('name',)
            call_command(
                'loaddatanaturally',
                'chroniker/tests/fixtures/jobs_by_name.json',
                traceback=True,
                verbosity=1)
            qs = Job.objects.all()
            # There are 3 jobs, but only 2 with unique names, so only two should have been created.
            self.assertEqual(qs.count(), 2)

            Job.objects.all().delete()

            settings.CHRONIKER_JOB_NK = ('command',)
            call_command(
                'loaddatanaturally',
                'chroniker/tests/fixtures/jobs_by_command.json',
                traceback=True,
                verbosity=1)
            qs = Job.objects.all()
            self.assertEqual(qs.count(), 2)

            Job.objects.all().delete()

            settings.CHRONIKER_JOB_NK = ('command', 'args')
            call_command(
                'loaddatanaturally',
                'chroniker/tests/fixtures/jobs_by_command_args.json',
                traceback=True,
                verbosity=1)
            qs = Job.objects.all()
            self.assertEqual(qs.count(), 3)

    def testMigration(self):
        """
        Ensure we can apply our initial migration without getting the error:

            Your models have changes that are not yet reflected in a migration,
            and so won't be applied.

        caused by various Django+Python versions having incompatible migration representations.
        """
        if django.VERSION > (1, 7, 0):
            ran = False
            for stdout_cls in (BytesIO, StringIO):
                stdout = stdout_cls()
                try:
                    call_command('migrate', 'chroniker', traceback=True, stdout=stdout)
                except TypeError:
                    continue
                ran = True
                stdout.seek(0)
                stdout = stdout.read()
                print('ret:', stdout)
                self.assertFalse('Your models have changes' in stdout)
                break
            self.assertTrue(ran)

    def testErrorCallback(self):

        job = Job.objects.all().update(enabled=False)

        while CALLBACK_ERRORS:
            CALLBACK_ERRORS.pop(0)
        self.assertFalse(CALLBACK_ERRORS)

        job = Job.objects.get(id=6)
        job.frequency = c.MINUTELY
        job.force_run = True
        job.enabled = True
        job.save()

        self.assertEqual(job.logs.all().count(), 0)
        #job.run(update_heartbeat=0)
        call_command('cron', update_heartbeat=0, sync=1)
        self.assertEqual(job.logs.all().count(), 1)
        self.assertEqual(len(CALLBACK_ERRORS), 1)

        # Simulate running the job 10 times.
        for _ in range(10):
            Job.objects.update()
            job = Job.objects.get(id=6)
            job.force_run = True
            job.save()
            call_command('cron', update_heartbeat=0, sync=1)
        for log in job.logs.all():
            print('log1:', log.id, log)
        self.assertEqual(job.logs.all().count(), 11)
        max_dt0 = job.logs.all().aggregate(Max('run_start_datetime'))['run_start_datetime__max']

        # Set max log entries to very low number, and confirm all old log entries are deleted.
        Job.objects.update()
        job = Job.objects.get(id=6)
        job.force_run = True
        job.maximum_log_entries = 3
        job.save()
        call_command('cron', update_heartbeat=0, sync=1)
        Job.objects.update()
        Log.objects.update()
        for log in job.logs.all():
            print('log2:', log.id, log)
        self.assertEqual(job.logs.all().count(), 3)
        max_dt1 = job.logs.all().aggregate(Max('run_start_datetime'))['run_start_datetime__max']
        print('max_dt0:', max_dt0)
        print('max_dt1:', max_dt1)
        self.assertTrue(max_dt1 > max_dt0)

    def testCronQueue(self):

        jobs = Job.objects.all()
        self.assertEqual(jobs.count(), 6)
        Job.objects.all().update(enabled=False)

        logs = Log.objects.all()
        self.assertEqual(logs.count(), 0)

        job = Job.objects.create(
            name='test',
            raw_command='ls',
            enabled=True,
            force_run=True,
            log_stdout=True,
            log_stderr=True,
        )

        time_start = time.time()
        # Note, if we run cron asynchronously, this breaks the transactions in Sqlite
        # and stops us from seeing model changes.
        call_command('cron', update_heartbeat=0, sync=1)
        time_end = time.time()

        Log.objects.update()
        logs = Log.objects.all()
        self.assertEqual(logs.count(), 1)

        Job.objects.update()
        job = Job.objects.get(id=job.id)
        logs = job.logs.all()
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs[0].stderr, '')
        print(logs[0].stdout)
        print(logs[0].stderr)
        self.assertEqual(job.last_run_successful, True)
        self.assertTrue(job.last_run_start_timestamp)

    def testHourly(self):

        Job.objects.all().delete()

        job = Job.objects.create(
            name='test',
            raw_command='ls',
            frequency=c.HOURLY,
            enabled=True,
            force_run=True,
            log_stdout=True,
            log_stderr=True,
        )
        self.assertEqual(job.logs.all().count(), 0)
        self.assertTrue(job.next_run)
        next_run0 = job.next_run.astimezone(pytz.utc)
        print('next_run0:', next_run0)
        self.assertTrue(timezone.is_aware(next_run0))
        self.assertEqual(next_run0.tzname(), 'UTC')

        # Initial next_run should be one-hour from now.
        td = next_run0 - timezone.now().astimezone(pytz.utc)
        print('td:', td)
        self.assertTrue(abs(td.total_seconds() -3600) <= 5)

        call_command('cron', update_heartbeat=0, sync=1)

        print('stdout:', job.logs.all()[0].stdout)
        print('stderr:', job.logs.all()[0].stderr)
        self.assertEqual(job.logs.all()[0].success, True)

        Job.objects.update()
        job = Job.objects.get(id=job.id)
        self.assertEqual(job.enabled, True)
        self.assertEqual(job.force_run, False)
        self.assertTrue(job.next_run)
        self.assertEqual(job.logs.all().count(), 1)
        next_run1 = job.next_run.astimezone(pytz.utc)
        print('next_run1:', next_run1)
        print('now:', timezone.now().astimezone(pytz.utc))
        self.assertTrue(timezone.is_aware(next_run1))
        # All datetimes get normalized to UTC in the database.
        self.assertEqual(next_run1.tzname(), 'UTC')

        # Force run should have left the next_run unchanged.
        td = (next_run1 - next_run0)#.total_seconds()
        print('td:', td)
        self.assertEqual(td.total_seconds(), 0)

        job.next_run = timezone.now() - timedelta(seconds=3600)
        job.save()
        self.assertEqual(job.is_due(), True)

        call_command('cron', update_heartbeat=0, sync=1)

        # The job should have been automatically scheduled to run an hour later.
        Job.objects.update()
        job = Job.objects.get(id=job.id)
        self.assertEqual(job.logs.all().count(), 2)
        next_run2 = job.next_run.astimezone(pytz.utc)
        print('next_run0:', next_run0)
        print('next_run2:', next_run2)
        #self.assertTrue(td.total_seconds())
        td2 = (next_run2 - timezone.now().astimezone(pytz.utc))
        print('td2:', td2)
        self.assertTrue(abs(td2.total_seconds() - 3600) <= 5)

    def testMarkRunning(self):
        _now = timezone.now
        try:
            job = Job.objects.get(id=1)
            job.mark_running()
            self.assertEqual(job.is_stale(), False)
            timezone.now = lambda: _now() + timedelta(minutes=settings.CHRONIKER_STALE_MINUTES*2)
            self.assertEqual(job.is_stale(), True)
        finally:
            timezone.now = _now

    def testJobFailure(self):

        user = User.objects.create(username='admin', email='admin@localhost')

        # Create a job that should fail and send an error email.
        Job.objects.all().delete()
        job = Job.objects.create(
            name='test error',
            command='test_error',
            frequency=c.HOURLY,
            enabled=True,
            force_run=True,
            log_stdout=True,
            log_stderr=True,
            email_errors_to_subscribers=True,
        )
        self.assertEqual(len(mail.outbox), 0)
        job.subscribers.add(user)
        job.save()
        self.assertEqual(job.email_errors_to_subscribers, True)
        self.assertEqual(Log.objects.all().count(), 0)

        # Run job.
        call_command('cron', update_heartbeat=0, sync=1)

        # Confirm an error email was sent.
        self.assertEqual(len(mail.outbox), 1)
        #print(mail.outbox[0].body)
        Job.objects.update()
        job = Job.objects.get(id=job.id)
        self.assertEqual(job.logs.all().count(), 1)
        print('log.id:', job.logs.all()[0].id)
        self.assertEqual(job.logs.all()[0].stdout, '')
        self.assertEqual(job.logs.all()[0].stderr, 'Something went wrong (but not really, this is just a test).\n')
        self.assertEqual(job.last_run_successful, False)

        # Create a job that should succeed and not send an error email.
        Job.objects.all().delete()
        job = Job.objects.create(
            name='test success',
            command='test_success',
            frequency=c.HOURLY,
            enabled=True,
            force_run=True,
            log_stdout=True,
            log_stderr=True,
            email_errors_to_subscribers=True,
        )
        while len(mail.outbox):
            mail.outbox.pop(0)
        self.assertEqual(len(mail.outbox), 0)
        job.subscribers.add(user)
        job.save()
        self.assertEqual(Log.objects.all().count(), 0)

        # Run job.
        call_command('cron', update_heartbeat=0, sync=1)

        # Confirm an error email was not sent.
        if len(mail.outbox):
            print(mail.outbox[0].body)
        self.assertEqual(len(mail.outbox), 0)
        Job.objects.update()
        job = Job.objects.get(id=job.id)
        self.assertEqual(job.logs.all().count(), 1)
        self.assertEqual(job.logs.all()[0].stdout, 'Everything is ok.\n')
        self.assertEqual(job.logs.all()[0].stderr, '')
        self.assertEqual(job.last_run_successful, True)

    def test_widgets(self):
        print('django.version:', django.VERSION)
        from chroniker import widgets
