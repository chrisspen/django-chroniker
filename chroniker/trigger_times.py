"""Convert Advanced Python scheduler style schedule trigger to
rrules with frequency and next run. APScheduler syntax is more
human readable then rrules and used in job SCHEDULE definitions"""

from datetime import datetime, timedelta, time
from dateutil import rrule


def days_range(day_of_week):
    """
    Returns rrule weekdays for a mon-fri style day range string

    >>> days_range('mon-fri')
    (MO, TU, WE, TH, FR)
    >>> days_range('tue-sat')
    (TU, WE, TH, FR, SA)
    """
    days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    start, end = day_of_week.split('-')
    return rrule.weekdays[days.index(start): days.index(end)+1]


def time_range(arg):
    """
    Parses time ranges and csv lists of hours or minutes returning lists of scheduled times

    >>> time_range('2-7')
    [2, 3, 4, 5, 6, 7]
    >>> time_range(3)
    [3]
    >>> time_range('16,21,23')
    [16, 21, 23]
    """
    if isinstance(arg, int) or arg.isdigit():
        return [arg]
    if '-' in arg:
        start, end = arg.split('-')
        return list(range(int(start), int(end)+1))
    if ',' in arg:
        return [int(x) for x in arg.split(',')]
    return []


def range_to_str(r):
    """Formats time_range or day_range lists for a human readable rrule"""
    return ','.join([str(x) for x in r])


def get_next_run(day_of_week='', hour=0, minute=0, second=0, minutes=False):
    """Converts APscheduler style schedules to chroniker style
    frequency, next run time and rrules such as: interval:15;byhour:7,8,9

    Run at 2020-07-10 11am to illustrate,
    would need time freezegun for the 1st two tests to pass

    >>> get_next_run(hour=20, minute=0, second=0)
    'DAILY', '2020-07-10', '20:00:00'
    >>> get_next_run(hour=5}
    'DAILY', '2020-07-11', '05:00:00'
    >>> get_next_run(day_of_week='mon-sun', hour='16,21,23', minute=20)
    'HOURLY', None, 'byweekday:MO,TU,WE,TH,FR,SA,SU;byhour:16,21,23;byminute:20'
    >>> get_next_run(day_of_week='mon-fri', hour='2-7', minute='15,45')
    'HOURLY', None, 'byweekday:MO,TU,WE,TH,FR;byhour:2,3,4,5,6,7;byminute:15,45
    >>> get_next_run(day_of_week='tue-sat', hour=4, minute=10)
    'HOURLY', None, 'byweekday:TU,WE,TH,FR,SA;byhour:4;byminute:10'
    >>> get_next_run(minutes=2)
    'MINUTELY', None, 'interval:2'
    """
    now = datetime.now()
    tmw = now + timedelta(days=1)

    # once a day
    if hour and not day_of_week:
        next_run = datetime(now.year, now.month, now.day, hour, minute, second)
        next_run_time = time(hour, minute, second)
        if now.time() > next_run_time:
            next_run = datetime(tmw.year, tmw.month, tmw.day, hour, minute, second)
        return 'DAILY', next_run, ''

    # hourly
    if day_of_week:
        days = range_to_str(days_range(day_of_week))
        hours = range_to_str(time_range(hour))
        mints = range_to_str(time_range(minute))

        return 'HOURLY', None, f'byweekday:{days};byhour:{hours};byminute:{mints}'

    # interval
    if minutes:
        return 'MINUTELY', None, f'interval:{minutes}'
