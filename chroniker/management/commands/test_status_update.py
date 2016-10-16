from __future__ import print_function

import time
from optparse import make_option

from django.core.management.base import BaseCommand

from chroniker.models import Job, Log

class Command(BaseCommand):
    help = 'Incrementally updates status, to help testing transaction ' + \
        'behavior on different database backends.'
    
    option_list = BaseCommand.option_list + (
        make_option('--seconds',
            dest='seconds',
            default=60,
            help='The number of total seconds to count up to.'),
        )
    
    def handle(self, *args, **options):
        seconds = int(options['seconds'])
        for i in xrange(seconds):
            Job.update_progress(total_parts=seconds, total_parts_complete=i)
            print('%i of %i' % (i, seconds))
            time.sleep(1)
