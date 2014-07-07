from __future__ import print_function

import os
import datetime
from datetime import timedelta
import time
import socket
import threading
from functools import cmp_to_key

socket.gethostname = lambda: 'localhost'

import six

from django.core.management import _commands, call_command
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

from chroniker.models import Job, Log, order_by_dependencies
from chroniker.tests.commands import Sleeper, InfiniteWaiter, ErrorThrower
from chroniker.management.commands.cron import run_cron

import warnings
warnings.simplefilter('error', RuntimeWarning)

from multiprocessing import Process

class JobProcess(Process):
    
    def run(self):
        while 1:
            #print('Waiting (pid=%i)...' % (os.getpid(),))
            time.sleep(1)

class JobTestCase(TestCase):
    
    fixtures = ['test_jobs.json']
    
    def setUp(self):
        # Install the test command; this little trick installs the command
        # so that we can refer to it by name
        _commands['test_sleeper'] = Sleeper()
        _commands['test_waiter'] = InfiniteWaiter()
        _commands['test_error'] = ErrorThrower()
    
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
            self.assertAlmostEqual(time_taken, time_expected, delta=4)
    
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
        self.assertAlmostEqual(time_taken, time_expected, delta=3.5)
    
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
        
        j1 = Job.objects.get(id=1)
        j2 = Job.objects.get(id=2)
        j3 = Job.objects.get(id=3)
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
        
        jobs = sorted(
            Job.objects.filter(enabled=True),
            key=cmp_to_key(order_by_dependencies))
#        for job in jobs:
#            print(job, [_.dependee for _ in job.dependencies.all()])
        self.assertEqual(jobs, [j1, j6, j4, j3, j2])
        
        # Ensure all dependent jobs come after their dependee job.
        due = Job.objects.due_with_met_dependencies_ordered()
        #print('due:', due)
        self.assertEqual(
            due,
            [
                Job.objects.get(id=6),
                Job.objects.get(id=1),
                Job.objects.get(id=4),
                Job.objects.get(id=3),# depends on 4
                Job.objects.get(id=2),# depends on 1 and 3
            ])
        
        # Note, possible bug? call_command() causes all models
        # changes made within the command to be lost.
        # e.g. Even though it appears to correctly run the job,
        # querying the job's next_run date will show the old original date.
        # As a workaround for testing, we just run them all directly.
        #call_command('cron', update_heartbeat=0)
        for job in due:
            job.run(update_heartbeat=0)
        
        #Job.objects.update()
        due = list(Job.objects.due_with_met_dependencies())
        #print('due:', due)
        self.assertEqual(
            due,
            [
                #Job.objects.get(args="5"),
            ])
        
        for job in due:
            job.run(update_heartbeat=0)
            
        due = list(Job.objects.due_with_met_dependencies())
        #print('due:', due)
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
            j.next_run = datetime.datetime(2014, 6, 27, 14, 31, 4)#, tzinfo=timezone.get_default_timezone())
            j.save()
        finally:
            settings.USE_TZ = True
            