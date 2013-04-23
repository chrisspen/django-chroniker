import time

from django.core.management.base import BaseCommand, CommandError

class Sleeper(BaseCommand):
    args = '[time in seconds to loop]'
    help = 'A simple command that simply sleeps for the specified duration'
    
    def handle(self, target_time, **options):
        start_time = time.time()
        target_time = float(target_time)
        
        print "Sleeping for %s seconds..." % (target_time,)
        time.sleep(target_time)
        
        end_time = time.time()
        print "Job ran for %f seconds" % (end_time-start_time)