import logging
import os
import sys
import time

from django.core.management.base import BaseCommand
from django.db import connection

from multiprocessing import Process

from chroniker.models import Job

class JobProcess(Process):
    """
    Each ``Job`` gets run in it's own ``Process``.
    """
    daemon = True
    
    def __init__(self, job, *args, **kwargs):
        self.job = job
        Process.__init__(self, *args, **kwargs)
        
        # Don't let this process hold up the parent.
        self.daemon = True
    
    def run(self):
        print "Running Job: '%s'" % self.job
        # TODO:Fix? Remove multiprocess and just running all jobs serially?
        # Multiprocessing does not play well with Django's PostgreSQL
        # connection, as it seems Django's connection code is not thread-safe.
        # It's a hacky solution, but the short-term fix seems to be to close
        # the connection in this thread, forcing Django to open a new
        # connection unique to this thread.
        connection.close()
        self.job.run()

class Command(BaseCommand):
    help = 'Runs all jobs that are due.'
    
    def handle(self, *args, **options):
        
        procs = []
        for job in Job.objects.due():
            if job.check_is_running():
                # Don't run if already running.
                continue
            elif not job.dependencies_met():
                # Don't run if dependencies aren't met.
                continue
            # Only run the Job if it isn't already running
            proc = JobProcess(job)
            proc.start()
            procs.append(proc)
        
        print "%d Jobs are due" % len(procs)
        
        # Keep looping until all jobs are done
        while procs:
            for proc in list(procs):
                if not proc.is_alive():
                    print 'Process %s ended.' % (proc,)
                    procs.remove(proc)
            time.sleep(.1)
