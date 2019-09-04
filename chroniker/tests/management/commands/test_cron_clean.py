from django.core.management import call_command
from django.test import TestCase


class CommandTest(TestCase):

    def test_command_executes_successfully(self):
        call_command('cron_clean', 'minutes', 1)
        call_command('cron_clean', 'hours', 1)
        call_command('cron_clean', 'days', 1)
        call_command('cron_clean', 'weeks', 1)
