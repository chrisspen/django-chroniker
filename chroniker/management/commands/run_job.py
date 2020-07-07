import sys
from distutils.version import StrictVersion # pylint: disable=E0611
from optparse import make_option

import django
from django.core.management.base import BaseCommand

from chroniker.models import Job


class Command(BaseCommand):

    help = 'Runs a specific job. The job will only run if it is not ' + \
        'currently running.'

    args = "job.id"

    option_list = getattr(BaseCommand, 'option_list', ()) + (
        make_option('--update_heartbeat',
            dest='update_heartbeat',
            default=1,
            help='If given, launches a thread to asynchronously update ' + \
                'job heartbeat status.'),
        )

    def create_parser(self, prog_name, subcommand):
        """
        For ``Django>=1.10``
        Create and return the ``ArgumentParser`` which extends ``BaseCommand`` parser with
        chroniker extra args and will be used to parse the arguments to this command.
        """
        parser = super(Command, self).create_parser(prog_name, subcommand)
        version_threshold = StrictVersion('1.10')
        current_version = StrictVersion(django.get_version(django.VERSION))
        if current_version >= version_threshold:
            parser.add_argument('args', nargs="*")
            parser.add_argument('--update_heartbeat',
                dest='update_heartbeat',
                default=1,
                help='If given, launches a thread to asynchronously update ' + \
                    'job heartbeat status.')
            self.add_arguments(parser)
        return parser

    def handle(self, *args, **options):
        for job_id in args:

            try:
                job = Job.objects.get(pk=int(job_id))
            except Job.DoesNotExist:
                sys.stderr.write("The requested Job %s does not exist.\n" % job_id)
                return

            # Run the job and wait for it to finish
            print('Attempting to run job %i...' % (job.id,))
            job.handle_run(update_heartbeat=int(options['update_heartbeat']))
