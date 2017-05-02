from __future__ import print_function

import sys
from optparse import make_option

import django
from django.core.management.base import BaseCommand

import six

from chroniker.models import get_current_job

class Command(BaseCommand):
    help = 'Runs a specific monitoring routine.'

    option_list = getattr(BaseCommand, 'option_list', ()) + (
        make_option('--imports',
            dest='imports',
            help='Modules to import.'),
        make_option('--query',
            dest='query',
            help='The query to run.'),
        make_option('--verbose',
            dest='verbose',
            default=False,
            help='If given, displays extra logging messages.'),
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
            parser.add_argument('--imports',
                dest='imports',
                help='Modules to import.')
            parser.add_argument('--query',
                dest='query',
                help='The query to run.')
            parser.add_argument('--verbose',
                dest='verbose',
                default=False,
                help='If given, displays extra logging messages.')
            self.add_arguments(parser)
        return parser

    def handle(self, *args, **options):
        imports = options['imports']
        query = options['query']
        verbose = options['verbose']
        assert imports, 'No imports specified.'
        assert query, 'No query specified.'
        for imp in imports.strip().split('|'):
            imp_parts = tuple(imp.split(','))
            if len(imp_parts) == 1:
                cmd = ('import %s' % imp_parts)
            elif len(imp_parts) == 2:
                cmd = ('from %s import %s' % imp_parts)
            elif len(imp_parts) == 3:
                cmd = ('from %s import %s as %s' % imp_parts)
            else:
                raise Exception('Invalid import: %s' % (imp,))
            if verbose:
                print(cmd)
            six.exec_(cmd)
        if verbose:
            print(query)
        q = eval(query, globals(), locals()) # pylint: disable=W0123

        job = get_current_job()
        if job:
            job.monitor_records = q.count()
            job.save()

        if q.count():
            print('%i records require attention.' % (q.count(),), file=sys.stderr)
        else:
            print('%i records require attention.' % (q.count(),), file=sys.stdout)
