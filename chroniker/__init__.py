from django import VERSION as DJANGO_VERSION


VERSION = (1, 0, 23)
__version__ = '.'.join(map(str, VERSION))

if DJANGO_VERSION < (3, 2):
    default_app_config = 'chroniker.apps.ChronikerConfig'
