import sys

from django.core.management.base import BaseCommand

from chroniker.models import Job


class Command(BaseCommand):

    help = 'Runs a specific job. The job will only run if it is not currently running.'

    def add_arguments(self, parser):
        parser.add_argument('args', nargs="*", help='job.id')
        parser.add_argument('--update_heartbeat',
            dest='update_heartbeat',
            default=1,
            help='If given, launches a thread to asynchronously update ' + \
                'job heartbeat status.')

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
