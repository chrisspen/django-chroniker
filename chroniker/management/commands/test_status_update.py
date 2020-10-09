import time

from django.core.management.base import BaseCommand

from chroniker.models import Job


class Command(BaseCommand):
    help = 'Incrementally updates status, to help testing transaction behavior on different database backends.'

    def add_arguments(self, parser):
        parser.add_argument('args', nargs="*")
        parser.add_argument('--seconds', dest='seconds', default=60, help='The number of total seconds to count up to.')

    def handle(self, *args, **options):
        seconds = int(options['seconds'])
        for i in range(seconds):
            Job.update_progress(total_parts=seconds, total_parts_complete=i)
            print('%i of %i' % (i, seconds))
            time.sleep(1)
