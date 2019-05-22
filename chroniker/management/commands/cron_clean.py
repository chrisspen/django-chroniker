from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from chroniker.models import Log


class Command(BaseCommand):
    help = 'Deletes old job logs.'

    def add_arguments(self, parser):
        parser.add_argument('unit', choices=['minutes', 'hours', 'days', 'weeks'])
        parser.add_argument('amount', type=int)

    def handle(self, *args, **options):
        unit = options['unit']
        amount = options['amount']
        kwargs = {unit: amount}
        time_ago = timezone.now() - timedelta(**kwargs)
        Log.cleanup(time_ago)
