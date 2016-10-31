from django.utils.translation import ugettext_lazy as _

YEARLY = 'YEARLY'
MONTHLY = 'MONTHLY'
WEEKLY = 'WEEKLY'
DAILY = 'DAILY'
HOURLY = 'HOURLY'
MINUTELY = 'MINUTELY'
SECONDLY = 'SECONDLY'

FREQ_CHOICES = (
    (YEARLY, _("Yearly")),
    (MONTHLY, _("Monthly")),
    (WEEKLY, _("Weekly")),
    (DAILY, _("Daily")),
    (HOURLY, _("Hourly")),
    (MINUTELY, _("Minutely")),
    (SECONDLY, _("Secondly")),
)

RRULE_WEEKDAY_DICT = {
    "MO": 0,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "FR": 4,
    "SA": 5,
    "SU": 6,
}

DEFAULT_MONITOR_ERROR_TEMPLATE = '''
The monitor "{{ job.name }}" has indicated a problem.

Please review this monitor at {{ url }}

{{ job.monitor_description_safe }}

{{ stderr }}
'''

WALL_CLOCK_TIME = 'wall-clock-time'

CPU_TIME = 'cpu-time'

RECURSIVE_CPU_TIME = 'recursive-cpu-time'

MAX_TIME = 'max-time' # max(WALL_CLOCK_TIME, RECURSIVE_CPU_TIME)
