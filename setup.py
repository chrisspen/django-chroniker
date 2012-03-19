from setuptools import setup, find_packages

import os
import urllib

import chroniker

def get_reqs(reqs=[]):
    # optparse is included with Python <= 2.7, but has been deprecated in favor
    # of argparse.  We try to import argparse and if we can't, then we'll add
    # it to the requirements
    try:
        import argparse
    except ImportError:
        reqs.append("argparse>=1.1")
    return reqs

setup(
    name = "django-chroniker",
    version = chroniker.__version__,
    packages = find_packages(),
    scripts = ['bin/chroniker'],
    package_data = {
        '': ['docs/*.txt', 'docs/*.py'],
        'chroniker': [
            'templates/*.*',
            'templates/*/*.*',
            'templates/*/*/*.*',
            'fixtures/*'
        ],
    },
    author = "Chris Spencer",
    author_email = "chrisspen@gmail.com",
    description = "",
    license = "BSD",
    url = "https://github.com/chrisspen/django-chroniker",
    classifiers = [
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
    zip_safe = False,
    install_requires = get_reqs(["Django>=1.0", "python-dateutil<=1.5"]),
    dependency_links = [
        'http://labix.org/download/python-dateutil/python-dateutil-1.5.tar.gz',
    ]
)
