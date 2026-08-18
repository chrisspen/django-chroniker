from __future__ import print_function

import time

import django
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = '[time in seconds to loop]'
    help = 'A simple command that simply sleeps for the specified duration'

    def create_parser(self, prog_name, subcommand):
        parser = super().create_parser(prog_name, subcommand)
        if django.VERSION >= (1, 10):
            parser.add_argument('target_time')
            self.add_arguments(parser)
        return parser

    def handle(self, target_time, **options):
        start_time = time.time()
        target_time = float(target_time)

        print("Sleeping for {} seconds...".format(target_time))
        time.sleep(target_time)

        end_time = time.time()
        print("Job ran for {} seconds".format(end_time - start_time))
