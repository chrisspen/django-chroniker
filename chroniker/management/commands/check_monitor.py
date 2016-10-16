from __future__ import print_function

import sys
import importlib
from datetime import timedelta
from optparse import make_option

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

import six

from chroniker.models import Job, Log, get_current_job

class Command(BaseCommand):
    help = 'Runs a specific monitoring routine.'
    
    option_list = BaseCommand.option_list + (
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
