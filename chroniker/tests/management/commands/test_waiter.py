from __future__ import print_function
import sys
import time

from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    args = ''
    help = 'A simple command that waits indefinitely.'
    
    def handle(self, *args, **options):
        while 1:
            time.sleep(1)
            print('Waiting...')
            