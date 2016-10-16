from __future__ import print_function
import sys
import time

from django.core.management.base import BaseCommand, CommandError
            
class Command(BaseCommand):
    args = ''
    help = 'A simple command that always fails.'
    
    def handle(self, *args, **options):
        print(
            'Something went wrong (but not really, this is just a test).',
            file=sys.stderr)
