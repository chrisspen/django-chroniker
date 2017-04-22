from __future__ import print_function
import sys

from django.core.management.base import BaseCommand

class Command(BaseCommand):
    args = ''
    help = 'A simple command that always succeeds.'

    def handle(self, *args, **options):
        print('Everything is ok.', file=sys.stdout)
