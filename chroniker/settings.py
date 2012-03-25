from django.conf import settings

def _get_name():
    from socket import gethostname
    from getpass import getuser
    return '%s@%s' % (getuser(), gethostname())

# Number of seconds that a lock file must be "stale" for a Job to be considered
# "dead".  Default is 1 minute (60 seconds)
LOCK_TIMEOUT = getattr(settings, 'CHRONIKER_LOCK_TIMEOUT', 60)

# The name used to identify the email sender.
EMAIL_SENDER = getattr(settings, 'CHRONIKER_EMAIL_SENDER', 
    getattr(settings, 'EMAIL_SENDER', None))
if not EMAIL_SENDER:
    EMAIL_SENDER = _get_name()

# The email address used to identify the email sender.
EMAIL_HOST_USER = getattr(settings, 'CHRONIKER_EMAIL_HOST_USER', 
    getattr(settings, 'EMAIL_HOST_USER', None))
if not EMAIL_HOST_USER:
    EMAIL_HOST_USER = _get_name()

EMAIL_SUBJECT_SUCCESS = getattr(
    settings,
    'CHRONIKER_EMAIL_SUBJECT_SUCCESS',
    'Success: {{ job.name }}')

EMAIL_SUBJECT_ERROR = getattr(
    settings,
    'CHRONIKER_EMAIL_SUBJECT_ERROR',
    'Error: {{ job.name }}')
