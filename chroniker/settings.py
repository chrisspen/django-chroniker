from django.conf import settings

def _get_name():
    from socket import gethostname
    from getpass import getuser
    return '%s@%s' % (getuser(), gethostname())

# Number of seconds that a lock file must be "stale" for a Job to be considered
# "dead".  Default is 1 minute (60 seconds)
settings.CHRONIKER_LOCK_TIMEOUT = getattr(
    settings,
    'CHRONIKER_LOCK_TIMEOUT',
    60)

# The name used to identify the email sender.
settings.CHRONIKER_EMAIL_SENDER = getattr(
    settings,
    'CHRONIKER_EMAIL_SENDER',
    getattr(
        settings,
        'EMAIL_SENDER',
        _get_name()
    ))

# The email address used to identify the email sender.
settings.CHRONIKER_EMAIL_HOST_USER = getattr(
    settings,
    'CHRONIKER_EMAIL_HOST_USER', 
    getattr(
        settings,
        'EMAIL_HOST_USER',
        _get_name()
    ))

settings.CHRONIKER_EMAIL_SUBJECT_SUCCESS = getattr(
    settings,
    'CHRONIKER_EMAIL_SUBJECT_SUCCESS',
    'Success: {{ job.name }}')

settings.CHRONIKER_EMAIL_SUBJECT_ERROR = getattr(
    settings,
    'CHRONIKER_EMAIL_SUBJECT_ERROR',
    'Error: {{ job.name }}')

settings.CHRONIKER_PID_FN = getattr(
    settings,
    'CHRONIKER_PID_FN',
    '/tmp/chroniker-cron.pid')

# If true, uses a PID file to ensure the cron management command only runs
# one at a time.
# TODO: unnecessary? deprecate?
settings.CHRONIKER_USE_PID = getattr(
    settings,
    'CHRONIKER_USE_PID',
    False)

settings.CHRONIKER_SELECT_FOR_UPDATE = getattr(
    settings,
    'CHRONIKER_SELECT_FOR_UPDATE',
    True)

# Set this to false for use on multiple hosts, since
# the lock file will only be accessible on a single host.
# The database will be used as effective lock.
# Recommend setting CHRONIKER_SELECT_FOR_UPDATE = True.
# Only set this to true if only a single host will ever read and write
# to the Job table.
settings.CHRONIKER_CHECK_LOCK_FILE = getattr(
    settings,
    'CHRONIKER_CHECK_LOCK_FILE',
    False)
