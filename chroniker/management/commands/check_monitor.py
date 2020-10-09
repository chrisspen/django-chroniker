from __future__ import print_function

import sys

from django.core.management.base import BaseCommand

from chroniker.models import get_current_job


class Command(BaseCommand):
    help = 'Runs a specific monitoring routine.'

    def add_arguments(self, parser):
        parser.add_argument('args', nargs="*")
        parser.add_argument('--imports', dest='imports', help='Modules to import.')
        parser.add_argument('--query', dest='query', help='The query to run.')
        parser.add_argument('--verbose', dest='verbose', default=False, help='If given, displays extra logging messages.')

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
            exec(cmd) # pylint: disable=exec-used
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
