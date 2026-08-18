import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Emits records through the logging module, for testing log capture.'

    def handle(self, *args, **options):
        print('printed line')
        logger.info('logged info line')
        logger.warning('logged warning line')
