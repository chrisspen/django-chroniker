import sys
from optparse import make_option

from django.core.management import call_command
from django.core.management.base import BaseCommand

from chroniker.models import Job, Log

class Command(BaseCommand):
    
    help = 'Runs a specific job. The job will only run if it is not ' + \
        'currently running.'
        
    args = "job.id"
    
    option_list = BaseCommand.option_list + (
        make_option('--update_heartbeat',
            dest='update_heartbeat',
            default=1,
            help='If given, launches a thread to asynchronously update ' + \
                'job heartbeat status.'),
        )
    
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
            