from __future__ import print_function
 
from setuptools import setup, find_packages, Command
from setuptools.command.test import test as TestCommand

import os
import sys
import urllib

import chroniker

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))

def get_reqs(*fns):
    lst = []
    for fn in fns:
        for package in open(os.path.join(CURRENT_DIR, fn)).readlines():
            package = package.strip()
            if not package:
                continue
            lst.append(package.strip())
    return lst

setup(
    name="django-chroniker",
    version=chroniker.__version__,
    packages=find_packages(),
    scripts=['bin/chroniker'],
    package_data={
        '': ['docs/*.txt', 'docs/*.py'],
        'chroniker': [
            'static/*/*/*.*',
            'templates/*.*',
            'templates/*/*.*',
            'templates/*/*/*.*',
            'templates/*/*/*/*.*',
            'fixtures/*',
            'tests/fixtures/*',
        ],
    },
    author="Chris Spencer",
    author_email="chrisspen@gmail.com",
    description="Easily control cron jobs via Django's admin.",
    license="BSD",
    url="https://github.com/chrisspen/django-chroniker",
    #https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 6 - Mature',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Framework :: Django',
    ],
    zip_safe=False,
    install_requires=get_reqs('pip-requirements-min-django.txt', 'pip-requirements.txt'),
    tests_require=get_reqs('pip-requirements-test.txt'),
)
