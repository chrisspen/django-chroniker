import os

PROJECT_DIR = os.path.dirname(__file__)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # Don't do this. It dramatically slows down the test.
        #        'NAME': '/tmp/chroniker.db',
        #        'TEST_NAME': '/tmp/chroniker.db',
    }
}

ROOT_URLCONF = 'chroniker.tests.urls'

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.sites',
    'chroniker',
    'chroniker.tests',
    'admin_steroids',
]

MEDIA_ROOT = os.path.join(PROJECT_DIR, 'media')


# Disable migrations.
# http://stackoverflow.com/a/28560805/247542
class DisableMigrations:

    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return "notmigrations"


USE_TZ = True

TIME_ZONE = 'America/New_York'

AUTH_USER_MODEL = 'auth.User'

SECRET_KEY = 'abc123'

SITE_ID = 1

BASE_SECURE_URL = 'https://localhost'

BASE_URL = 'http://localhost'

MIDDLEWARE_CLASSES = MIDDLEWARE = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    #'django.middleware.transaction.TransactionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.locale.LocaleMiddleware',
)

CHRONIKER_JOB_ERROR_CALLBACK = 'chroniker.tests.tests.job_error_callback'

# Required in Django>=1.10.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            '%s/../templates' % PROJECT_DIR,
            '%s/../static' % PROJECT_DIR,
        ],
        #         'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
            ],
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
            'debug':
            True,
        },
    },
]
