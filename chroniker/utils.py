from __future__ import print_function
from __future__ import unicode_literals

import os
import sys
import time
import signal
import warnings
import errno
from multiprocessing import Process, current_process
from importlib import import_module
from datetime import timedelta
try:
    from io import StringIO
except ImportError:
    from cStringIO import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import models
from django.db import connection
from django.utils import timezone
from django.conf import settings
from django.utils.encoding import smart_str

import psutil

from six import print_, reraise, u

from . import constants as c

def get_etc(complete_parts, total_parts, start_datetime, current_datetime=None, as_seconds=False):
    """
    Estimates a job's expected time to completion.
    """
    current_datetime = current_datetime or timezone.now()

    # Calculate the seconds passed since we started tracking progress.
    passed_seconds = float((current_datetime - start_datetime).total_seconds())

    if total_parts:

        # Estimate the total seconds the task will take to complete by using
        # a linear projection.
        total_seconds = passed_seconds/complete_parts*total_parts

        # Estimate the expected time of completion by projecting the duration
        # onto the start time.
        etc = start_datetime + timedelta(seconds=total_seconds)

        # If we only want remaining seconds, return difference between ETC and
        # the current time in seconds.
        if as_seconds:
            return (etc - current_datetime).total_seconds()

        return etc

def get_remaining_seconds(*args, **kwargs):
    kwargs['as_seconds'] = True
    return get_etc(*args, **kwargs)

#def calculate_eta(start_datetime, start_count, current_count, total_count):
#    """
#    Returns the datetime when the given process will likely complete, assuming
#    a relatively linear projection of the current progress.
#    """
#    assert start_count >= 0, 'Invalid start_count: %s' % (start_count,)
#    assert current_count >= 0, 'Invalid current_count: %s' % (current_count,)
#    assert total_count >= 0, 'Invalid total_count: %s' % (total_count,)
#    assert isinstance(start_datetime, datetime)
#    if not total_count:
#        return
#    now_datetime = datetime.now()
#    ran_parts = current_count - start_count
#    ran_seconds = (now_datetime - start_datetime).total_seconds()
#    remaining_parts = total_count - current_count - start_count
#    if not ran_parts:
#        return
#    remaining_seconds = ran_seconds/float(ran_parts)*remaining_parts
#    eta = now_datetime + timedelta(seconds=remaining_seconds)
#    return eta

def get_admin_change_url(obj):
    ct = ContentType.objects.get_for_model(obj)
    change_url_name = 'admin:%s_%s_change' % (ct.app_label, ct.model)
    return reverse(change_url_name, args=(obj.id,))

def get_admin_changelist_url(obj):
    ct = ContentType.objects.get_for_model(obj)
    list_url_name = 'admin:%s_%s_changelist' % (ct.app_label, ct.model)
    return reverse(list_url_name)

class TeeFile(StringIO):
    """
    A helper class for allowing output to be stored in a StringIO instance
    while still be directed to a second file object, such as sys.stdout.
    """
    def __init__(self, file, auto_flush=False, queue=None, local=True): # pylint: disable=W0622
        super(TeeFile, self).__init__()
        #StringIO.__init__(self)
        self.file = file
        self.auto_flush = auto_flush
        self.length = 0
        self.queue = queue
        self.queue_buffer = []

        # If False, tracks length, but doesn't store content locally.
        # Useful if you want to keep track of whether or not data was written
        # but don't care about the content, especially if it's expected to be massive.
        self.local = local

    def write(self, s):
        try:
            #import chardet
            #encoding_opinion = chardet.detect(s)
            #encoding = encoding_opinion['encoding']
            #TODO:fix? not stripping out non-ascii characters result in error
            #'ascii' codec can't encode character ? in position ?: ordinal not in range(128)
            s = ''.join(_ for _ in s if ord(_) < 128)
            #s = s.encode(encoding, 'ignore')
        except ImportError:
            pass
        self.length += len(s)
        self.file.write(s)
        if self.local:
            #super(TeeFile, self).write(s)
            StringIO.write(self, s)
        if self.auto_flush:
            #self.file.flush()
            self.flush()
        if self.queue is not None:
            self.queue_buffer.append(s)

    def flush(self):
        self.file.flush()
        #super(TeeFile, self).flush()
        StringIO.flush(self)
        if self.queue is not None:
            data = (current_process().pid, ''.join(self.queue_buffer)) # pylint: disable=E1102
            self.queue.put(data)
            self.queue_buffer = []

    def fileno(self):
        return self.file.fileno()

# Based on:
# http://djangosnippets.org/snippets/833/
# http://www.shiningpanda.com/blog/2012/08/08/mysql-table-lock-django/
class LockingManager(models.Manager):
    """ Add lock/unlock functionality to manager.

    Example::

        class Job(models.Model):

            manager = LockingManager()

            counter = models.IntegerField(null=True, default=0)

            @staticmethod
            def do_atomic_update(job_id)
                ''' Updates job integer, keeping it below 5 '''
                try:
                    # Ensure only one HTTP request can do this update at once.
                    Job.objects.lock()

                    job = Job.object.get(id=job_id)
                    # If we don't lock the tables two simultanous
                    # requests might both increase the counter
                    # going over 5
                    if job.counter < 5:
                        job.counter += 1
                        job.save()

                finally:
                    Job.objects.unlock()


    """

    def lock(self):
        """ Lock table.

        Locks the object model table so that atomic update is possible.
        Simulatenous database access request pend until the lock is unlock()'ed.

        Note: If you need to lock multiple tables, you need to do lock them
        all in one SQL clause and this function is not enough. To avoid
        dead lock, all tables must be locked in the same order.

        See http://dev.mysql.com/doc/refman/5.0/en/lock-tables.html
        """
        cursor = connection.cursor()
        if 'mysql' in connection.settings_dict['ENGINE']:
            table = self.model._meta.db_table
            cursor.execute("LOCK TABLES %s WRITE" % table)
        else:
            warnings.warn(
                'Locking of database backend "%s" is not supported.'
                    % (connection.settings_dict['ENGINE'],),
                warnings.RuntimeWarning
            )
        #row = cursor.fetchone()
        #return row
        return cursor

    def unlock(self):
        """ Unlock the table. """
        cursor = connection.cursor()
        if 'mysql' in connection.settings_dict['ENGINE']:
            table = self.model._meta.db_table
            cursor.execute("UNLOCK TABLES")
        else:
            warnings.warn(
                '(Un)Locking of database backend "%s" is not supported.'
                    % (connection.settings_dict['ENGINE'],),
                warnings.RuntimeWarning
            )
        #row = cursor.fetchone()
        #return row
        return cursor

def pid_exists(pid):
    """
    Returns true if the process associated with the given PID is still running.
    Returns false otherwise.
    """
    pid = int(pid)
    if pid < 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno == errno.EPERM
    else:
        return True

def get_cpu_usage(pid, interval=1):
    """
    Returns the CPU usage, as reported by `ps`, of the process associated with
    the given PID.
    """
#    cmd = ['ps', '-p', str(pid), '-o', '%cpu', '--no-headers']
#    output = subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()[0]
#    try:
#        return float(output.strip().split('\n')[0])
#    except ValueError:
#        return
    return psutil.Process(pid).get_cpu_times(interval=interval)

def kill_process(pid):
    """
    Kills the process associated with the given PID.
    Returns true if the process was successfully killed.
    Returns false otherwise.
    """
    pid = int(pid)
    try:

        # Try sending a keyboard interrupt.
        os.kill(pid, signal.SIGINT) # 2
        if not pid_exists(pid):
            return True

        # Ask politely again.
        os.kill(pid, signal.SIGABRT) # 6
        if not pid_exists(pid):
            return True

        # Try once more.
        os.kill(pid, signal.SIGTERM) # 15
        if not pid_exists(pid):
            return True

        # We've asked nicely and we've been ignored, so just murder it.
        os.kill(pid, signal.SIGKILL) # 9
        if not pid_exists(pid):
            return True

    except OSError:
        # Something strange happened.
        # Our user likely doesn't have permission to kill the process.
        return False

class TimedProcess(Process):
    """
    Helper to allow us to time a specific chunk of code and determine when
    it has reached a timeout.

    Also, this conveniently allows us to kill the whole thing if it locks up
    or takes too long, without requiring special coding in the target code.
    """

    daemon = True

    def __init__(self, max_seconds, time_type=c.MAX_TIME, fout=None, check_freq=1, *args, **kwargs):
        super(TimedProcess, self).__init__(*args, **kwargs)
        self.fout = fout or sys.stdout
        self.t0 = time.clock()
        self.t0_objective = time.time()
        self.max_seconds = float(max_seconds)
        self.t1 = None
        self.t1_objective = None
        # The number of seconds the process waits between checks.
        self.check_freq = check_freq
        self.time_type = time_type
        self._p = None
        self._process_times = {} # {pid:user_seconds}
        self._last_duration_seconds = None

    def terminate(self, sig=15, *args, **kwargs):
        """
        sig := 6=abrt, 9=kill, 15=term
        """
        if self.is_alive() and self._p:
            # Explicitly kill children since the default terminate() doesn't
            # seem to do this very reliably.
            for child in self._p.get_children():
                # Do one last time check.
                self._process_times[child.pid] = child.get_cpu_times().user
                os.system('kill -%i %i' % (sig, child.pid,))
            # Sum final time.
            self._process_times[self._p.pid] = self._p.get_cpu_times().user
            self._last_duration_seconds = sum(self._process_times.itervalues())
        os.system('kill -%i %i' % (sig, self._p.pid,))
        #return super(TimedProcess, self).terminate(*args, **kwargs)

    def get_duration_seconds_wall(self):
        if self.t1_objective is not None:
            return self.t1_objective - self.t0_objective
        return time.time() - self.t0_objective

    def get_duration_seconds_cpu(self):
        if self.t1 is not None:
            return self.t1 - self.t0
        return time.clock() - self.t0

    def get_duration_seconds_cpu_recursive(self):
        # Note, this calculation will consume much user
        # CPU time itself than simply checking clock().
        # Recommend using larger check_freq to minimize this.
        # Note, we must store historical child times because child
        # processes may die, causing them to no longer be included in
        # future calculations, possibly corrupting the total time.
        self._process_times[self._p.pid] = self._p.get_cpu_times().user
        children = self._p.get_children(recursive=True)
        for child in children:
            self._process_times[child.pid] = child.get_cpu_times().user
        #TODO:optimize by storing total sum and tracking incremental changes?
        return sum(self._process_times.itervalues())

    def get_cpu_usage_recursive(self, interval=1):
        usage = 0
        try:
            usage = self._p.get_cpu_percent(interval=interval)
            children = self._p.get_children(recursive=True)
            for child in children:
                try:
                    usage += child.get_cpu_percent(interval=interval)
                except psutil._error.NoSuchProcess:
                    pass
        except psutil._error.NoSuchProcess:
            pass
        return usage

    def get_duration_seconds_max(self):
        return max(
            self.get_duration_seconds_wall(),
            self.get_duration_seconds_cpu_recursive(),
        )

    def get_duration_seconds(self):
        """
        Retrieve the number of seconds this process has been executing for.

        If process was instantiated with objective=True, then the wall-clock
        value is returned.

        Otherwise the user-time is returned.
        If recursive=True is given, recursively finds all child-processed,
        if any, and includes their user-time in the total calculation.
        """
        if self.is_alive():
            if self.time_type == c.WALL_CLOCK_TIME:
                return self.get_duration_seconds_wall()
            elif self.time_type == c.CPU_TIME:
                return self.get_duration_seconds_cpu()
            elif self.time_type == c.RECURSIVE_CPU_TIME:
                return self.get_duration_seconds_cpu_recursive()
            elif self.time_type == c.MAX_TIME:
                return self.get_duration_seconds_max()
            else:
                raise NotImplementedError

    @property
    def is_expired(self):
        if not self.max_seconds:
            return False
        duration_seconds = self.get_duration_seconds()
        return duration_seconds >= self.max_seconds

    @property
    def seconds_until_timeout(self):
        return max(self.max_seconds - self.get_duration_seconds(), 0)

    def start(self, *args, **kwargs):
        super(TimedProcess, self).start(*args, **kwargs)
        self._p = psutil.Process(self.pid)

    def start_then_kill(self, verbose=True):
        """
        Starts and then kills the process if a timeout occurs.

        Returns true if a timeout occurred. False if otherwise.
        """
        self.start()
        timeout = False
        while 1:
            time.sleep(1)
            if verbose:
                self.fout.write('\r\t%.0f seconds until timeout.' \
                    % (self.seconds_until_timeout,))
                self.fout.flush()
            if not self.is_alive():
                break
            elif self.is_expired:
                if verbose:
                    print_('\nAttempting to terminate expired process %s...' \
                        % (self.pid,), file=self.fout)
                timeout = True
                self.terminate()
        self.t1 = time.clock()
        self.t1_objective = time.time()
        return timeout

def make_naive(dt, tz):
    if timezone.is_aware(dt):
        return timezone.make_naive(dt, tz)
    return dt

def make_aware(dt, tz):
    if dt is None:
        return
    elif settings.USE_TZ:
        if timezone.is_aware(dt):
            return dt
        else:
            return timezone.make_aware(dt, tz)
    else:
        if timezone.is_aware(dt):
            return timezone.make_naive(dt)
        else:
            return dt

def localtime(dt):
    dt = make_aware(dt, settings.TIME_ZONE)
    return dt

def write_lock(lock_file):
    lock_file.seek(0)
    lock_file.write(str(time.time()).encode('utf-8'))
    lock_file.flush()

# Backportted from Django 1.7.
def import_string(dotted_path):
    """
    Import a dotted module path and return the attribute/class designated by the
    last name in the path. Raise ImportError if the import failed.
    """

    try:
        from django.utils.module_loading import import_string # pylint: disable=W0621
        return import_string(dotted_path)
    except ImportError:
        pass

    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError:
        msg = "%s doesn't look like a module path" % dotted_path
        reraise(ImportError, ImportError(msg), sys.exc_info()[2])

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError:
        msg = 'Module "%s" does not define a "%s" attribute/class' % (
            dotted_path, class_name)
        reraise(ImportError, ImportError(msg), sys.exc_info()[2])

def smart_print(*args, **kwargs):
    """
    Attempts to print, respecting encoding, across all Python versions.
    """
    encoding = kwargs.pop('encoding', 'utf8')
    s = smart_str(' ')
    s = s.join(args)
    try:
        print(u(s).encode(encoding), **kwargs)
    except TypeError:
        try:
            print(smart_str(s, encoding=encoding), **kwargs)
        except TypeError:
            print(s, **kwargs)
