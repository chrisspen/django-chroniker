"""Setup jobs in Chroniker from a collection of argh python scripts in a folder

CHRONIKER_JOBS_FOLDER is a folder as well as a python module containing a collection of jobs
Each job is a submodule containing a SCHEDULE variable, jobs have functions to execute
exposed as CLI commands using python argh.

Importlib module is used to examine job scripts.
The docstrings of these job functions are pulled as job descriptions into Chroniker.

SCHEDULE variable is used to setup rrule and frequency of execution.
It can look like this:

SCHEDULE = {
    'import_data': dict(day_of_week='mon-fri', hour='2-7', minute='15,45'),
    'backup_files': ...
}

All jobs on settings.CHRONIKER_JOBS_LIST from within settings.CHRONIKER_JOBS_FOLDER will be setup
using their function exposed via SCHEDULE. All CHRONIKER_JOBS_DISABLED will be setup disabled,
CHRONIKER_JOBS_SUBSCRIBERS will be signed up to receive errors.
"""

from chroniker.models import Job, Log
from chroniker.trigger_times import get_next_run
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection
from django.contrib.auth.models import User
from django.conf import settings

import importlib


def reset_models(models):
    """Delete all data for a model and reset ID counters
    Used to hard reset all Jobs and Logs in Chroniker
    """

    for m in models:
        m.objects.all().delete()

    # set autoincrement to zero using sequence_reset_sql
    srs = connection.ops.sequence_reset_sql(no_style(), models)
    with connection.cursor() as cursor:
        for sql in srs:
            cursor.execute(sql)


def setup_jobs(reset=False):
    """Examines jobs files and re-creates jobs as specified resetting first"""
    if reset:
        reset_models([Job, Log])
    for module in settings.CHRONIKER_JOBS_LIST:
        setup_module(module)


def setup_module(module, enabled=True, prefix=''):
    """Create jobs for module using its SCHEDULE
    >>> setup_module('job_module', enabled=False, prefix='FM')
    """
    print(module)
    schedules = get_schedules(module)

    # instruct jobs with commands, schedules and params creating children jobs
    for subcommand, schedule in schedules.items():
        instruct_job(module, prefix, subcommand, schedule, enabled=enabled)


def instruct_job(module, prefix, subcommand, schedule, enabled=True):
    """Creates a job and schedules it"""
    module_name = module if not prefix else f'{prefix} {module}'
    module_name = module_name.replace('_', ' ')
    argh_command = subcommand.replace('_', '-')
    command_name = subcommand.replace('_', ' ')
    raw_command = f'python3 -m {settings.CHRONIKER_JOBS_FOLDER}.{module} {argh_command}'
    if not schedule or module in settings.CHRONIKER_JOBS_DISABLED:
        enabled = False

    job, _created = Job.objects.get_or_create(
        name=f'{module_name} {command_name}',
        defaults=dict(raw_command=raw_command, enabled=enabled)
    )
    job.description = get_description(module, subcommand)
    job.raw_command = raw_command
    job.save()
    if not schedule:
        return
    print(job.name, schedule)
    frequency, next_run, rrules = get_next_run(**schedule)
    print('   ', frequency, next_run, rrules)
    job.frequency = frequency
    job.next_run = next_run
    job.params = rrules
    users = staff_accounts(settings.CHRONIKER_JOBS_SUBSCRIBERS)
    job.subscribers.add(*users)  # add e-markets and operations users to all job errors
    job.save()


def staff_accounts(subscribers):
    """Returns staff accounts for error subscribes creating them if they don't exist"""

    users = []
    for username, email in subscribers.items():
        u, created = User.objects.get_or_create(username=username, defaults={'email': email})
        if created:
            u.set_password(username.title()+'2020!')
            u.is_staff = True
            u.save()
        users.append(u)
    return users


def get_description(module_name, function_name=None):
    """Get description docstring of a module or its function"""
    module = importlib.import_module(f'{settings.CHRONIKER_JOBS_FOLDER}.{module_name}')
    x = module
    if function_name:
        func = module.__dict__.get(function_name)
        if func and func.__doc__:
            x = func
        else:
            return ''
    return x.__doc__.strip().split('\n\n')[0]


def get_schedules(module_name):
    """Get schedules for a given module"""
    return importlib.import_module(
        f'{settings.CHRONIKER_JOBS_FOLDER}.{module_name}'
    ).__dict__.get('SCHEDULE')


class Command(BaseCommand):
    """
    Recreate the job database

    Empty logs and job tables, when -f option is used.
    """
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('-f', '--force', action='store_true',
                            help='Reset jobs and logs')

    def handle(self, *args, **options):
        force_reset = options.get('force', False)
        setup_jobs(force_reset)
