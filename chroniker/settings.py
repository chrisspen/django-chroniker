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
settings.CHRONIKER_USE_PID = getattr(
    settings,
    'CHRONIKER_USE_PID',
    True)
