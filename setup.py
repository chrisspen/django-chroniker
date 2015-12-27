from __future__ import print_function
 
from setuptools import setup, find_packages, Command
from setuptools.command.test import test as TestCommand

import os
import sys
import urllib

import chroniker

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))

def get_reqs(fn):
    return [
        _.strip()
        for _ in open(os.path.join(CURRENT_DIR, fn)).readlines()
        if _.strip()
    ]

# class TestCommand(Command):
#     description = "Runs unittests."
#     user_options = [
#         ('name=', None,
#          'Name of the specific test to run. e.g. testTimezone'),
#         ('virtual-env-dir=', None,
#          'The location of the virtual environment to use.'),
#         ('pv=', None,
#          'The version of Python to use. e.g. 2.7 or 3'),
#         ('dv=', None,
#          'The version of Django to use. e.g. 1.7 or 1.8'),
#     ]
#     
#     def initialize_options(self):
#         self.name = None
#         self.virtual_env_dir = './.env%s-%s'
#         self.pv = 0
#         self.python_versions = [2.7, 3, 3.4]
#         self.dv = 0
#         self.django_versions = [
#             1.5,
#             1.6, # last version without native migrations
#             1.7, # built-in migration support
#             1.8,
#         ]
#         
#     def finalize_options(self):
#         pass
#     
#     def build_virtualenv(self, pv, dv):
#         virtual_env_dir = self.virtual_env_dir % (pv, dv)
#         kwargs = dict(virtual_env_dir=virtual_env_dir, pv=pv, dv=dv)
#         if not os.path.isdir(virtual_env_dir):
#             cmd = 'virtualenv -p /usr/bin/python{pv} {virtual_env_dir}'.format(**kwargs)
#             print(cmd)
#             os.system(cmd)
#             
#             cmd = '. {virtual_env_dir}/bin/activate; easy_install -U distribute; deactivate'.format(**kwargs)
#             print(cmd)
#             os.system(cmd)
#             
#             for package in get_reqs(dv=dv):
#                 kwargs['package'] = package
#                 cmd = '. {virtual_env_dir}/bin/activate; pip install -U {package}; deactivate'.format(**kwargs)
#                 print(cmd)
#                 os.system(cmd)
#     
#     def run(self):
#         
#         python_versions = self.python_versions
#         if self.pv:
#             python_versions = [self.pv]
#             
#         django_versions = self.django_versions
#         if self.dv:
#             django_versions = [self.dv]
#         
#         for dv in django_versions:
#             dv = float(dv)
#             for pv in python_versions:
#                 
#                 self.build_virtualenv(pv=pv, dv=dv)
#                 test_name_prefix = 'chroniker.'
#                 if dv <= 1.5:
#                     test_name_prefix = ''
#                 kwargs = dict(
#                     pv=pv,
#                     dv=dv,
#                     name=self.name,
#                     test_name_prefix=test_name_prefix,
#                     virtual_env_dir = self.virtual_env_dir % (pv, dv))
#                     
#                 if self.name:
#                     cmd = '. {virtual_env_dir}/bin/activate; django-admin.py test --pythonpath=. --traceback --settings=chroniker.tests.settings {test_name_prefix}tests.tests.JobTestCase.{name}; deactivate'.format(**kwargs)
#                 else:
#                     cmd = '. {virtual_env_dir}/bin/activate; django-admin.py test --pythonpath=. --traceback --settings=chroniker.tests.settings {test_name_prefix}tests; deactivate'.format(**kwargs)
#                     
#                 print(cmd)
#                 ret = os.system(cmd)
#                 if ret:
#                     print('Failed for pv=%s dv=%s.' % (pv, dv))
#                     return

class Tox(TestCommand):

    user_options = [
        ('name=', None,
         'Name of the specific test to run. e.g. testTimezone'),
#         ('virtual-env-dir=', None,
#          'The location of the virtual environment to use.'),
        ('pv=', None,
        'The version of Python to use. e.g. 2.7 or 3'),
        ('dv=', None,
        'The version of Django to use. e.g. 1.7 or 1.8'),
    ]
    
    def initialize_options(self):
        self.name = None
        self.pv = 0
        #self.python_versions = [2.7, 3, 3.4]
        self.dv = 0
#         self.django_versions = [
#             1.5,
#             1.6, # last version without native migrations
#             1.7, # built-in migration support
#             1.8,
#         ]
        self.test_args = []
        self.test_suite = True
        
    def finalize_options(self):
        pass
#         TestCommand.finalize_options(self)
#         self.name = None
#         self.pv = 0
#         self.dv = 0
#         self.test_args = []
#         self.test_suite = True

    def run_tests(self):
#         import tox
#         import shlex
        #args = self.tox_args
        #if args:
        #    args = shlex.split(self.tox_args)
        print('-'*80)
        print('self.test_args:',self.test_args)
        print('name:',self.name)
#         errno = tox.cmdline()#self.test_args)
#         sys.exit(errno)

setup(
    name = "django-chroniker",
    version = chroniker.__version__,
    packages = find_packages(),
    scripts = ['bin/chroniker'],
    package_data = {
        '': ['docs/*.txt', 'docs/*.py'],
        'chroniker': [
            'static/*/*/*.*',
            'templates/*.*',
            'templates/*/*.*',
            'templates/*/*/*.*',
            'templates/*/*/*/*.*',
            'fixtures/*',
        ],
    },
    author = "Chris Spencer",
    author_email = "chrisspen@gmail.com",
    description = "Easily control cron jobs via Django's admin.",
    license = "BSD",
    url = "https://github.com/chrisspen/django-chroniker",
    #https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers = [
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.0',
        'Programming Language :: Python :: 3.4',
        'Framework :: Django',
    ],
    zip_safe = False,
    install_requires=get_reqs('pip-requirements.txt'),
    tests_require=get_reqs('pip-requirements-test.txt'),
#    dependency_links = [
#        'http://labix.org/download/python-dateutil/python-dateutil-1.5.tar.gz',
#    ]
    cmdclass={
        #'test': TestCommand,
        'test': Tox,
    },
)
