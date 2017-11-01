#from distutils.version import StrictVersion
from django.conf import settings

#DJANGO_VERSION = StrictVersion(django.get_version())

def _get_name():
    from socket import gethostname
    from getpass import getuser
    return '%s@%s' % (getuser(), gethostname())

# Number of seconds that a lock file must be "stale" for a Job to be considered
# "dead".  Default is 1 minute (60 seconds)
CHRONIKER_LOCK_TIMEOUT = settings.CHRONIKER_LOCK_TIMEOUT = getattr(
    settings,
    'CHRONIKER_LOCK_TIMEOUT',
    60)

# The name used to identify the email sender.
CHRONIKER_EMAIL_SENDER = settings.CHRONIKER_EMAIL_SENDER = getattr(
    settings,
    'CHRONIKER_EMAIL_SENDER',
    getattr(
        settings,
        'EMAIL_SENDER',
        _get_name()
    ))

# The email address used to identify the email sender.
CHRONIKER_EMAIL_HOST_USER = settings.CHRONIKER_EMAIL_HOST_USER = getattr(
    settings,
    'CHRONIKER_EMAIL_HOST_USER',
    getattr(
        settings,
        'EMAIL_HOST_USER',
        _get_name()
    ))

CHRONIKER_EMAIL_SUBJECT_SUCCESS = settings.CHRONIKER_EMAIL_SUBJECT_SUCCESS = getattr(
    settings,
    'CHRONIKER_EMAIL_SUBJECT_SUCCESS',
    'Success: {{ job.name }}')

CHRONIKER_EMAIL_SUBJECT_ERROR = settings.CHRONIKER_EMAIL_SUBJECT_ERROR = getattr(
    settings,
    'CHRONIKER_EMAIL_SUBJECT_ERROR',
    'Error: {{ job.name }}')

CHRONIKER_PID_FN = settings.CHRONIKER_PID_FN = getattr(
    settings,
    'CHRONIKER_PID_FN',
    '/tmp/chroniker-cron.pid')

# If true, uses a PID file to ensure the cron management command only runs
# one at a time.
# TODO: unnecessary? deprecate?
CHRONIKER_USE_PID = settings.CHRONIKER_USE_PID = getattr(
    settings,
    'CHRONIKER_USE_PID',
    False)

# Setting this to True causes each process to acquire a lock on the job
# table while looking for the next job to run.
# This ensures no race-conditions where two proceses happen to both
# choose the same jobs before the other can mark them as running.
# WARNING: In cases where buggy management commands don't properly
# close or end their transaction, setting this to True will result
# in `manage.py cron` blocking indefinitely while it waits for the previous
# process to free the lock. If this is being run by the system cron once
# a minute, then these processes will build up until all database connections
# and memory are exhausted.
# Only set this to True if you really need this functionality and
# are certain transactions are properly maintained in all of your scheduled
# commands.
CHRONIKER_SELECT_FOR_UPDATE = settings.CHRONIKER_SELECT_FOR_UPDATE = getattr(
    settings,
    'CHRONIKER_SELECT_FOR_UPDATE',
    False)

# Set this to false for use on multiple hosts, since
# the lock file will only be accessible on a single host.
# The database will be used effectively as the lock.
# Recommend setting CHRONIKER_SELECT_FOR_UPDATE = True.
# Only set this to true if only a single host will ever read and write
# to the Job table.
CHRONIKER_CHECK_LOCK_FILE = settings.CHRONIKER_CHECK_LOCK_FILE = getattr(
    settings,
    'CHRONIKER_CHECK_LOCK_FILE',
    False)

# The number of minutes a job can go without updating its database record
# before it's considered stale.
CHRONIKER_STALE_MINUTES = settings.CHRONIKER_STALE_MINUTES = getattr(
    settings,
    'CHRONIKER_STALE_MINUTES',
    5)

# If true, and a job becomes stale, it will be automatically marked
# as not running, with a failed status and log entry noting that the
# job unexpectedly crashed.
CHRONIKER_AUTO_END_STALE_JOBS = settings.CHRONIKER_AUTO_END_STALE_JOBS = getattr(
    settings,
    'CHRONIKER_AUTO_END_STALE_JOBS',
    True)

CHRONIKER_JOB_NK = settings.CHRONIKER_JOB_NK = getattr(
    settings,
    'CHRONIKER_JOB_NK',
    ('name',))

CHRONIKER_JOB_ERROR_CALLBACK = settings.CHRONIKER_JOB_ERROR_CALLBACK = getattr(
    settings,
    'CHRONIKER_JOB_ERROR_CALLBACK',
    None)
