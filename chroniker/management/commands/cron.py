import logging
import os
import re
import sys
import time
import errno
import socket
import subprocess
from functools import partial
from optparse import make_option
from collections import defaultdict
from multiprocessing import Process, Queue

from django.core.management.base import BaseCommand
from django.db import connection
import django
from django.conf import settings
from django.utils import timezone

import psutil

from chroniker.models import Job, Log
from chroniker import constants as c
from chroniker import utils

def kill_stalled_processes(dryrun=True):
    """
    Due to a bug in the Django|Postgres backend, occassionally
    the `manage.py cron` process will hang even through all processes
    have been marked completed.
    We compare all recorded PIDs against those still running,
    and kill any associated with complete jobs.
    """
    pids = set(map(int, Job.objects\
        .filter(is_running=False, current_pid__isnull=False)\
        .exclude(current_pid='')\
        .values_list('current_pid', flat=True)))
    for pid in pids:
        try:
            if utils.pid_exists(pid):# and not utils.get_cpu_usage(pid):
                p = psutil.Process(pid)
                cmd = ' '.join(p.cmdline())
                if 'manage.py cron' in cmd:
                    jobs = Job.objects.filter(current_pid=pid)
                    job = None
                    if jobs:
                        job = jobs[0]
                    print('Killing process %s associated with %s.' % (pid, job))
                    if not dryrun:
                        utils.kill_process(pid)
                else:
                    print('PID not cron.')
            else:
                print('PID dead.')
        except psutil.NoSuchProcess:
            print('PID does not exist.')

class JobProcess(utils.TimedProcess):
    
    def __init__(self, job, *args, **kwargs):
        super(JobProcess, self).__init__(*args, **kwargs)
        self.job = job

def run_job(job, update_heartbeat=None, **kwargs):
    
    stdout_queue = kwargs.pop('stdout_queue', None)
    stderr_queue = kwargs.pop('stderr_queue', None)
    force_run = stderr_queue('force_run', False)
    
    # TODO:causes UnicodeEncodeError: 'ascii' codec can't encode
    # character u'\xa0' in position 59: ordinal not in range(128)
    #print(u"Running Job: %i - '%s' with args: %s" \
    #    % (job.id, job, job.args))
    
    # TODO:Fix? Remove multiprocess and just running all jobs serially?
    # Multiprocessing does not play well with Django's PostgreSQL
    # connection, as it seems Django's connection code is not thread-safe.
    # It's a hacky solution, but the short-term fix seems to be to close
    # the connection in this thread, forcing Django to open a new
    # connection unique to this thread.
    # Without this call to connection.close(), we'll get the error
    # "Lost connection to MySQL server during query".
    print('Closing connection.')
    connection.close()
    print('Connection closed.')
    job.run(
        update_heartbeat=update_heartbeat,
        check_running=False,
        stdout_queue=stdout_queue,
        stderr_queue=stderr_queue,
        force_run=force_run,
    )
    #TODO:mark job as not running if still marked?
    #TODO:normalize job termination and cleanup outside of handle_run()?

def run_cron(jobs=None, update_heartbeat=True, force_run=False, dryrun=False, clear_pid=False):
    try:
        
        # TODO: auto-kill inactive long-running cron processes whose
        # threads have stalled and not exited properly?
        # Check for 0 cpu usage.
        #ps -p <pid> -o %cpu
        
        stdout_map = defaultdict(list) # {prod_id:[]}
        stderr_map = defaultdict(list) # {prod_id:[]}
        stdout_queue = Queue()
        stderr_queue = Queue()
        
        if settings.CHRONIKER_AUTO_END_STALE_JOBS and not dryrun:
            Job.objects.end_all_stale()
            
        # Check PID file to prevent conflicts with prior executions.
        # TODO: is this still necessary? deprecate? As long as jobs run by
        # JobProcess don't wait for other jobs, multiple instances of cron
        # should be able to run simeltaneously without issue.
        if settings.CHRONIKER_USE_PID:
            pid_fn = settings.CHRONIKER_PID_FN
            pid = str(os.getpid())
            any_running = Job.objects.all_running().count()
            if not any_running:
                # If no jobs are running, then even if the PID file exists,
                # it must be stale, so ignore it.
                pass
            elif os.path.isfile(pid_fn):
                try:
                    old_pid = int(open(pid_fn, 'r').read())
                    if utils.pid_exists(old_pid):
                        print('%s already exists, exiting' % pid_fn)
                        sys.exit()
                    else:
                        print(('%s already exists, but contains stale '
                            'PID, continuing') % pid_fn)
                except ValueError:
                    pass
                except TypeError:
                    pass
            file(pid_fn, 'w').write(pid)
            clear_pid = True
        
        procs = []
        if force_run:
            q = Job.objects.all()
            if jobs:
                q = q.filter(id__in=jobs)
        else:
            q = Job.objects.due_with_met_dependencies_ordered(jobs=jobs)
        
        running_ids = set()
        for job in q:
            
            # This is necessary, otherwise we get the exception
            # DatabaseError: SSL error: sslv3 alert bad record mac
            # even through we're not using SSL...
            # We work around this by forcing Django to use separate
            # connections for each process by explicitly closing the
            # current connection.
            connection.close()
            
            # Re-check dependencies to incorporate any previous iterations
            # that marked jobs as running, potentially causing dependencies
            # to become unmet.
            Job.objects.update()
            job = Job.objects.get(id=job.id)
            if not force_run and not job.is_due_with_dependencies_met(running_ids=running_ids):
                print('Job %i %s is due but has unmet dependencies.' % (job.id, job))
                continue
            
            # Immediately mark the job as running so the next jobs can
            # update their dependency check.
            print('Running job %i %s.' % (job.id, job))
            running_ids.add(job.id)
            if dryrun:
                continue
            job.is_running = True
            Job.objects.filter(id=job.id).update(is_running=job.is_running)
            
            # Launch job.
            #proc = JobProcess(job, update_heartbeat=update_heartbeat, name=str(job))
            job_func = partial(
                run_job,
                job=job,
                force_run=force_run or job.force_run,
                update_heartbeat=update_heartbeat,
                name=str(job),
            )
            proc = JobProcess(
                job=job,
                max_seconds=job.timeout_seconds,
                target=job_func,
                name=str(job),
                kwargs=dict(
                    stdout_queue=stdout_queue,
                    stderr_queue=stderr_queue,
                ))
            proc.start()
            procs.append(proc)
        
        if not dryrun:
            print("%d Jobs are due." % len(procs))
            
            # Wait for all job processes to complete.
            while procs:
                
                while not stdout_queue.empty():
                    proc_id, proc_stdout = stdout_queue.get()
                    stdout_map[proc_id].append(proc_stdout)
                    
                while not stderr_queue.empty():
                    proc_id, proc_stderr = stderr_queue.get()
                    stderr_map[proc_id].append(proc_stderr)
                    
                for proc in list(procs):
                    
                    # Auto kill processes that haven't terminated but yet
                    # register no cpu usage.
                    #cpu = proc.get_cpu_usage_recursive()
                    #print('cpu:',proc,cpu)
#                    if not cpu:
#                        utils.kill_process(proc.pid)
#                        time.sleep(1)
                    
                    if not proc.is_alive():
                        print('Process %s ended.' % (proc,))
                        procs.remove(proc)
                    elif proc.is_expired:
                        print('Process %s expired.' % (proc,))
                        proc_id = proc.pid
                        proc.terminate()
                        run_end_datetime = timezone.now()
                        procs.remove(proc)
                        
                        connection.close()
                        Job.objects.update()
                        j = Job.objects.get(id=proc.job.id)
                        run_start_datetime = j.last_run_start_timestamp
                        proc.job.is_running = False
                        proc.job.force_run = False
                        proc.job.force_stop = False
                        proc.job.save()
                        
                        # Create log record since the job was killed before it had
                        # a chance to do so.
                        Log.objects.create(
                            job=proc.job,
                            run_start_datetime=run_start_datetime,
                            run_end_datetime=run_end_datetime,
                            success=False,
                            on_time=False,
                            hostname=socket.gethostname(),
                            stdout=''.join(stdout_map[proc_id]),
                            stderr=''.join(stderr_map[proc_id]+['Job exceeded timeout\n']),
                        )
                        
                time.sleep(1)
            print('!'*80)
            print('All jobs complete!')
    finally:
        if settings.CHRONIKER_USE_PID and os.path.isfile(pid_fn) \
        and clear_pid:
            os.unlink(pid_fn)


class Command(BaseCommand):
    help = 'Runs all jobs that are due.'
    option_list = getattr(BaseCommand, 'option_list', ()) + (
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
        make_option('--dryrun',
            action='store_true',
            default=False,
            help='If given, only displays jobs to be run.'),
        make_option('--jobs',
            dest='jobs',
            default='',
            help='A comma-delimited list of job ids to limit executions to.'),
        make_option('--name',
            dest='name',
            default='',
            help='A name to give this process.'),
    )

    def create_parser(self, prog_name, subcommand):
        """
        For ``Django>=1.10``
        Create and return the ``ArgumentParser`` which extends ``BaseCommand`` parser with
        chroniker extra args and will be used to parse the arguments to this command.
        """
        parser = super(Command, self).create_parser(prog_name, subcommand)
        from distutils.version import StrictVersion
        version_threshold = StrictVersion('1.10')
        current_version = StrictVersion(django.get_version(django.VERSION))
        if current_version >= version_threshold:
            parser.add_argument('--update_heartbeat',
                dest='update_heartbeat',
                default=1,
                help='If given, launches a thread to asynchronously update ' + \
                    'job heartbeat status.')
            parser.add_argument('--force_run',
                dest='force_run',
                action='store_true',
                default=False,
                help='If given, forces all jobs to run.')
            parser.add_argument('--dryrun',
                action='store_true',
                default=False,
                help='If given, only displays jobs to be run.')
            parser.add_argument('--jobs',
                dest='jobs',
                default='',
                help='A comma-delimited list of job ids to limit executions to.')
            parser.add_argument('--name',
                dest='name',
                default='',
                help='A name to give this process.')
            self.add_arguments(parser)
        return parser
    
    def handle(self, *args, **options):
        
        kill_stalled_processes(dryrun=False)
        
        # Find specific job ids to run, if any.
        jobs = [
            int(_.strip())
            for _ in options.get('jobs', '').strip().split(',')
            if _.strip().isdigit()
        ]
        update_heartbeat = int(options['update_heartbeat'])
        force_run = options['force_run']
        run_cron(
            jobs,
            update_heartbeat=update_heartbeat,
            force_run=force_run,
            dryrun=options['dryrun'],
        )
