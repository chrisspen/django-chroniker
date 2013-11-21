import logging
import os
import sys
import time
import errno
from optparse import make_option

from django.core.management.base import BaseCommand
from django.db import connection
import django
from django.conf import settings

from multiprocessing import Process

from chroniker.models import Job
from chroniker import constants as c

def pid_exists(pid):
    """Check whether pid exists in the current process table."""
    if pid < 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError, e:
        return e.errno == errno.EPERM
    else:
        return True

class JobProcess(Process):
    """
    Each ``Job`` gets run in it's own ``Process``.
    """
    daemon = True
    
    def __init__(self, job, update_heartbeat=True, *args, **kwargs):
        self.job = job
        Process.__init__(self, *args, **kwargs)
        
        # Don't let this process hold up the parent.
        self.daemon = True
        self.update_heartbeat = update_heartbeat
    
    def run(self):
        print "Running Job: %i - '%s' with args: %s" \
            % (self.job.id, self.job, self.job.args)
        # TODO:Fix? Remove multiprocess and just running all jobs serially?
        # Multiprocessing does not play well with Django's PostgreSQL
        # connection, as it seems Django's connection code is not thread-safe.
        # It's a hacky solution, but the short-term fix seems to be to close
        # the connection in this thread, forcing Django to open a new
        # connection unique to this thread.
        # Without this call to connection.close(), we'll get the error
        # "Lost connection to MySQL server during query".
        print 'Closing connection.'
        connection.close()
        print 'Connection closed.'
        self.job.run(update_heartbeat=self.update_heartbeat)

class Command(BaseCommand):
    help = 'Runs all jobs that are due.'
    option_list = BaseCommand.option_list + (
        make_option('--update_heartbeat',
            dest='update_heartbeat',
            default=1,
            help='If given, launches a thread to asynchronously update ' + \
                'job heartbeat status.'),
        make_option('--force_run',
            dest='force_run',
            action='store_true',
            default=False,
            help='If given, forces all jobs to run.'),
        make_option('--jobs',
            dest='jobs',
            default='',
            help='A comma-delimited list of job ids to limit executions to.'),
    )
    
    def handle(self, *args, **options):
        pid_fn = settings.CHRONIKER_PID_FN
        clear_pid = False
        
        # Find specific job ids to run, if any.
        jobs = [
            int(_.strip())
            for _ in options.get('jobs', '').strip().split(',')
            if _.strip().isdigit()
        ]
        
        try:
            update_heartbeat = int(options['update_heartbeat'])
            
            # TODO: auto-kill inactive long-running cron processes whose
            # threads have stalled and not exited properly?
            # Check for 0 cpu usage.
            #ps -p <pid> -o %cpu
            
            # Check PID file to prevent conflicts with prior executions.
            # TODO: is this still necessary? deprecate? As long as jobs run by
            # JobProcess don't wait for other jobs, multiple instances of cron
            # should be able to run simeltaneously without issue.
            if settings.CHRONIKER_USE_PID:
                pid = str(os.getpid())
                any_running = Job.objects.all_running().count()
                if not any_running:
                    # If no jobs are running, then even if the PID file exists,
                    # it must be stale, so ignore it.
                    pass
                elif os.path.isfile(pid_fn):
                    try:
                        old_pid = int(open(pid_fn, 'r').read())
                        if pid_exists(old_pid):
                            print '%s already exists, exiting' % pid_fn
                            sys.exit()
                        else:
                            print ('%s already exists, but contains stale '
                                'PID, continuing') % pid_fn
                    except ValueError:
                        pass
                    except TypeError:
                        pass
                file(pid_fn, 'w').write(pid)
                clear_pid = True
            
            procs = []
            if options['force_run']:
                q = Job.objects.all()
                if jobs:
                    q = q.filter(id__in=jobs)
            else:
                q = Job.objects.due_with_met_dependencies(jobs=jobs)
            for job in q:
                # Only run the Job if it isn't already running.
                proc = JobProcess(job, update_heartbeat=update_heartbeat, name=str(job))
                proc.start()
                procs.append(proc)
            
            print "%d Jobs are due" % len(procs)
            
            # Wait for all job processes to complete.
            while procs:
                for proc in list(procs):
                    if not proc.is_alive():
                        print 'Process %s ended.' % (proc,)
                        procs.remove(proc)
                time.sleep(.1)
                
        finally:
            if settings.CHRONIKER_USE_PID and os.path.isfile(pid_fn) \
            and clear_pid:
                os.unlink(pid_fn)
                