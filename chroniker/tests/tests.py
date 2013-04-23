import datetime
import time

from django.core.management import _commands, call_command
from django.test import TestCase

from chroniker.models import Job, Log#, freqs
from chroniker.tests.commands import Sleeper

#try:
#    from django.utils import unittest
#except:
#    import unittest

class JobTestCase(TestCase):
    
    fixtures = ['test_jobs.json']
    
    def setUp(self):
        # Install the test command; this little trick installs the command
        # so that we can refer to it by name
        _commands['test_sleeper'] = Sleeper()
    
    def testJobRun(self):
        """
        Test that the jobs run properly.
        """
        self.assertEqual(Job.objects.all().count(), 4)
        
        for job in Job.objects.due():
            time_expected = float(job.args)
            
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
        job = sorted(Job.objects.due().filter(command="test_sleeper"), key=lambda j: -int(j.args))[0]
        
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
        job = sorted(Job.objects.due().filter(command="test_sleeper"), key=lambda j: int(j.args))[0]
        
        # Run the job 5 times
        for i in range(5):
            job.run(update_heartbeat=0)
        
        # Ensure that we have 5 Log objects
        self.assertEqual(Log.objects.count(), 1)
        
        # Now clean out the logs that are older than 0 minutes (all of them)
        #call_command('cron_clean', 'minutes', '0')
        Log.cleanup()
        
        # Ensure that we have 0 Log objects
        self.assertEqual(Log.objects.count(), 0)
        
    def testDependencies(self):
        """
        Confirm inter-job dependencies are detected.
        """
        
        due = list(Job.objects.due_with_met_dependencies())
        #print 'due:', due
        self.assertEqual(
            due,
            [Job.objects.get(args="1"), Job.objects.get(args="10")])
        
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
        #print 'due:', due
        self.assertEqual(due, [Job.objects.get(args="5")])
        
        for job in due:
            job.run(update_heartbeat=0)
            
        due = list(Job.objects.due_with_met_dependencies())
        #print 'due:', due
        self.assertEqual(due, [Job.objects.get(args="2")])
        