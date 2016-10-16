from __future__ import print_function

import os
import sys
import datetime
from datetime import timedelta
import time
import socket
import threading
import warnings
from functools import cmp_to_key
from multiprocessing import Process

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

from chroniker.models import Job, Log
from chroniker.tests.commands import Sleeper, InfiniteWaiter, ErrorThrower
from chroniker.management.commands.cron import run_cron
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
        while 1:
            #print('Waiting (pid=%i)...' % (os.getpid(),))
            time.sleep(1)

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
        
        Job.objects.end_all_stale()
        
        job = Job.objects.get(id=1)
        self.assertEqual(job.is_running, False)
        self.assertEqual(job.last_run_successful, False)

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
    
    def testJobFailure(self):
        self.assertEqual(len(mail.outbox), 0)
        user = User.objects.create(username='admin', email='admin@localhost')
        job = Job.objects.get(id=6)
        job.subscribers.add(user)
        job.save()
        self.assertEqual(job.email_errors_to_subscribers, True)
        
        # Run job.
        job.run(update_heartbeat=0)
        
        # Confirm an error email was sent.
        self.assertEqual(len(mail.outbox), 1)
        #print(mail.outbox[0].body)
    
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
        
        stdout_str = job.logs.all()[0].stdout
        self.assertEqual(stdout_str, 'hello\n')
        
        stderr_str = job.logs.all()[0].stderr
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
            try:
                #astimezone() cannot be applied to a naive datetime
                timezone.make_naive(j.next_run, timezone=tz)
                self.assertTrue(0)
            except ValueError:
                pass
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
        
        while CALLBACK_ERRORS:
            CALLBACK_ERRORS.pop(0)
        self.assertFalse(CALLBACK_ERRORS)
        
        job = Job.objects.get(id=6)
        job.frequency = c.MINUTELY
        job.force_run = True
        job.enabled = True
        job.save()
        
        self.assertEqual(job.logs.all().count(), 0)
        job.run(update_heartbeat=0)
        self.assertEqual(job.logs.all().count(), 1)
        self.assertEqual(len(CALLBACK_ERRORS), 1)
