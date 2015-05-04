 
from setuptools import setup, find_packages, Command

import os
import sys
import urllib

import chroniker

def get_reqs(dv=None):
    # optparse is included with Python <= 2.7, but has been deprecated in favor
    # of argparse.  We try to import argparse and if we can't, then we'll add
    # it to the requirements
    reqs = []
    
    if dv is not None:
        dv = float(dv)
        reqs.append('Django==%s' % dv)
    else:
        reqs.append('Django>=1.5')
        
    reqs.extend([
        'python-dateutil>=2.2',
        'psutil>=2.1.1',
        'six>=1.7.2',
    ])
    
    try:
        import argparse
    except ImportError:
        reqs.append('argparse>=1.1')
    return reqs

class TestCommand(Command):
    description = "Runs unittests."
    user_options = [
        ('name=', None,
         'Name of the specific test to run. e.g. testTimezone'),
        ('virtual-env-dir=', None,
         'The location of the virtual environment to use.'),
        ('pv=', None,
         'The version of Python to use. e.g. 2.7 or 3'),
        ('dv=', None,
         'The version of Django to use. e.g. 1.7 or 1.8'),
    ]
    
    def initialize_options(self):
        self.name = None
        self.virtual_env_dir = './.env%s-%s'
        self.pv = 0
        self.python_versions = [2.7, 3, 3.4]
        self.dv = 0
        self.django_versions = [
            1.5,
            1.6, # last version without native migrations
            1.7, # built-in migration support
            1.8,
        ]
        
    def finalize_options(self):
        pass
    
    def build_virtualenv(self, pv, dv):
        virtual_env_dir = self.virtual_env_dir % (pv, dv)
        kwargs = dict(virtual_env_dir=virtual_env_dir, pv=pv, dv=dv)
        if not os.path.isdir(virtual_env_dir):
            cmd = 'virtualenv -p /usr/bin/python{pv} {virtual_env_dir}'.format(**kwargs)
            print(cmd)
            os.system(cmd)
            
            cmd = '. {virtual_env_dir}/bin/activate; easy_install -U distribute; deactivate'.format(**kwargs)
            print(cmd)
            os.system(cmd)
            
            for package in get_reqs(dv=dv):
                kwargs['package'] = package
                cmd = '. {virtual_env_dir}/bin/activate; pip install -U {package}; deactivate'.format(**kwargs)
                print(cmd)
                os.system(cmd)
    
    def run(self):
        
        python_versions = self.python_versions
        if self.pv:
            python_versions = [self.pv]
            
        django_versions = self.django_versions
        if self.dv:
            django_versions = [self.dv]
        
        for dv in django_versions:
            dv = float(dv)
            for pv in python_versions:
                
                self.build_virtualenv(pv=pv, dv=dv)
                test_name_prefix = 'chroniker.'
                if dv <= 1.5:
                    test_name_prefix = ''
                kwargs = dict(
                    pv=pv,
                    dv=dv,
                    name=self.name,
                    test_name_prefix=test_name_prefix,
                    virtual_env_dir = self.virtual_env_dir % (pv, dv))
                    
                if self.name:
                    cmd = '. {virtual_env_dir}/bin/activate; django-admin.py test --pythonpath=. --traceback --settings=chroniker.tests.settings {test_name_prefix}tests.tests.JobTestCase.{name}; deactivate'.format(**kwargs)
                else:
                    cmd = '. {virtual_env_dir}/bin/activate; django-admin.py test --pythonpath=. --traceback --settings=chroniker.tests.settings {test_name_prefix}tests; deactivate'.format(**kwargs)
                    
                print(cmd)
                ret = os.system(cmd)
                if ret:
                    print('Failed for pv=%s dv=%s.' % (pv, dv))
                    return

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
    install_requires = get_reqs(),
#    dependency_links = [
#        'http://labix.org/download/python-dateutil/python-dateutil-1.5.tar.gz',
#    ]
    cmdclass={
        'test': TestCommand,
    },
)
