
from datetime import datetime, timedelta

import logging
import sys

from django.core.management.base import BaseCommand

from chroniker.models import Log

class Command(BaseCommand):
    help = 'Deletes old job logs.'
    
    def handle(self, *args, **options):
                
        if len(args) != 2:
            sys.stderr.write(
                'Command requires two arguments. '
                'Unit (weeks, days, hours or minutes) and interval.\n')
            return
        else:
            unit = str(args[0])
            if unit not in ['weeks', 'days', 'hours', 'minutes']:
                sys.stderr.write('Valid units are weeks, days, hours or minutes.\n')
                return
            try:
                amount = int(args[1]) 
            except ValueError:
                sys.stderr.write('Interval must be an integer.\n')
                return
        kwargs = {unit: amount}
        time_ago = datetime.now() - timedelta(**kwargs)
        #Log.objects.filter( run_start_datetime__lte = time_ago ).delete()
        Log.cleanup(time_ago)
