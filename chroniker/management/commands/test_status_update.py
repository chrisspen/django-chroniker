from __future__ import print_function

import time
from optparse import make_option

import django
from django.core.management.base import BaseCommand

from chroniker.models import Job

class Command(BaseCommand):
    help = 'Incrementally updates status, to help testing transaction ' + \
        'behavior on different database backends.'

    option_list = getattr(BaseCommand, 'option_list', ()) + (
        make_option('--seconds',
            dest='seconds',
            default=60,
            help='The number of total seconds to count up to.'),
        )

    def create_parser(self, prog_name, subcommand):
        """
        For ``Django>=1.10``
        Create and return the ``ArgumentParser`` which extends ``BaseCommand`` parser with
        chroniker extra args and will be used to parse the arguments to this command.
        """
        from distutils.version import StrictVersion # pylint: disable=E0611
        parser = super(Command, self).create_parser(prog_name, subcommand)
        version_threshold = StrictVersion('1.10')
        current_version = StrictVersion(django.get_version(django.VERSION))
        if current_version >= version_threshold:
            parser.add_argument('args', nargs="*")
            parser.add_argument('--seconds',
                dest='seconds',
                default=60,
                help='The number of total seconds to count up to.')
            self.add_arguments(parser)
        return parser

    def handle(self, *args, **options):
        seconds = int(options['seconds'])
        for i in range(seconds):
            Job.update_progress(total_parts=seconds, total_parts_complete=i)
            print('%i of %i' % (i, seconds))
            time.sleep(1)
