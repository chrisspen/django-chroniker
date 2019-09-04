Chroniker - Django Controlled Cron Jobs
=============================================================================

[![](https://img.shields.io/pypi/v/django-chroniker.svg)](https://pypi.python.org/pypi/django-chroniker) [![Build Status](https://img.shields.io/travis/chrisspen/django-chroniker.svg?branch=master)](https://travis-ci.org/chrisspen/django-chroniker) [![](https://pyup.io/repos/github/chrisspen/django-chroniker/shield.svg)](https://pyup.io/repos/github/chrisspen/django-chroniker)

Overview
--------

Django Chroniker is a Python package that allows
you to use cron to schedule Django management commands through Django's admin.

Creating cron jobs for Django apps can be a pain, annoying and repetitive.
With django-chroniker you simply create a single cron job to run every minute,
point it at your site's directory and run `manage.py cron`.
Then, you can create, update and delete jobs through Django's admin.

This is a fork of Weston Nielson's [Chronograph](https://bitbucket.org/wnielson/django-chronograph/) project.

Features
--------

This package contains the following improvements over the parent Chronograph project:

* Allow Django management commands to record their percent-progress and display it in admin. e.g.

        from chroniker.models import Job
        Job.update_progress(total_parts=77, total_parts_complete=13)
    
* Improved logging of management command stdout and stderr, and efficiently displaying these in admin.
* Creation of the `Monitor` model, a proxy of the `Job` model, to allow easier setup of system and database state monitoring.
* Addition of a model for documenting inter-job dependencies as well as flags for controlling job behavior based on these dependencies. e.g. You can configure one job to not run until another job has successfully run, or run at a later date.
* Improved support for coordinating job execution in a multi-server environment. e.g. You can configure a job to only run on a specific host or any host.

Unlike some scheduling systems, Chroniker attempts to ensure that every job may
have at most only one running instance at any given time. This greatly
simplifies scheduling, but necessarily imposes some restrictions. If you need
to schedule multiple instances of a task to run simultaneously, especially in
real-time, consider using a system like [Celery](http://www.celeryproject.org/)
instead.

Installation
------------

Install the package from PyPI via pip with:

    pip install django-chroniker
    
or directly from github with (warning, this may be less stable than the official release on PyPI):

    pip install https://github.com/chrisspen/django-chroniker/tarball/master
    
Add 'chroniker' and 'django.contrib.sites' to the `INSTALLED_APPS` list in your `settings.py` like:

    INSTALLED_APPS = (
    ...
    'django.contrib.sites',
    'chroniker',
    ...
    )

If you're using Django 1.7 or higher (which you should be), install Chroniker's models by running:

    python manage.py migrate
    
otherwise run:

    python manage.py syncdb

Usage
-----

In your admin, creating and jobs under the Chroniker section.

If you're in a development setting, you can test your Chroniker-based cron jobs by first checking "force run" on your job, and then running:

    python manage.py cron

Also, you can simulate a simple cron server that will automatically run any pending cron jobs every N seconds with:

    python manage.py cronserver

To allow Chroniker can send email, ensure you have valid email parameters in your settings.py. A very basic example using Gmail might be:

    EMAIL_USE_TLS = True
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_HOST_USER = 'myusername@gmail.com'
    EMAIL_HOST_PASSWORD = os.environ['GMAILPASS']

You can customize the "name" Chroniker uses in its emails with:

    CHRONIKER_EMAIL_SENDER = 'Jon Doe'

You can also specify a separate email user for Chroniker with:

    CHRONIKER_EMAIL_HOST_USER = 'someotherusername@otherdomain.com'

When installing Chroniker in a production environment, you'll need to add a single cron job that calls `bin/chroniker` or `python manage.py cron`.
Within the call, you'll need to specify where this script is installed, where your Python virtual environment is located (if you're using one), and where your Django project is located.
An example of this might be: 

    * * * * * /usr/local/myproject/bin/chroniker -e /usr/local/myproject/.env/bin/activate_this.py -p /usr/local/myproject

Run `bin/chroniker --help` for a full listing of options.

Settings
--------

Depending on your usage, there are a few options that could greatly help or harm job scheduling.

`CHRONIKER_USE_PID`

*   If this is set to True, the `cron` management command will wait for the previous run to complete using a local PID file.

`CHRONIKER_SELECT_FOR_UPDATE`

*   If this is set to True, the Job record [will be locked](https://docs.djangoproject.com/en/dev/ref/models/querysets/#select-for-update) when updating job status in the database. This may not be supported on all database backends.

`CHRONIKER_CHECK_LOCK_FILE`

*   If this is set to True, chroniker will check for a local lockfile to determine if the job is running or not.
*   You should set this to True in a single-server environment, and False in a multi-server environment.

`CHRONIKER_DISABLE_RAW_COMMAND`

*   If this is set to True, chroniker will not run raw commands. This reduces the attack surface in case less trusted people have access to the admin interface.

Maintenance
-----------

If you'd like an easy way to delete old job logs, there is a management command
that will do it for you: ``cron_clean``.  You can use it like so::

    python manage.py cron_clean [weeks|days|hours|minutes] [integer]

So, if you want to remove all jobs that are older than a week, you can do the
following::

    python manage.py cron_clean weeks 1

Since this is just a simple management command, you can also easily add it to
``chroniker``, via the admin, so that it will clear out old logs
automatically.

Tools
-----

There is anther included management command, ``cronserver`` which can be used
to test the periodic running of jobs.  It'll print out information to the
screen about which job are due and also run them.  Here is how you would use
it::

    python manage.py cronserver

This will start up a process that will check for and run any jobs that are due
every 60 seconds.  The interval can be changed by simply passing the number of
seconds in between runs.  For example, to make the process check for due jobs
every 2 minutes, you would run::

    python manage.py cronserver 120

Architecture
------------

The trickiest thing to get right in ``Chroniker`` is the ability to properly
manage the state of a ``Job``, i.e. reliably determining whether or not a
job is or isn't running, if it has been killed or terminated prematurely.  In
the first version of ``Chroniker`` this issue was "solved" by keeping track
of the PID of each running job and using the ``ps`` command to have the
operating system tell us if the job was still running.  However, this route was
less than ideal, for a few reasons, but most importantly because isn't wasn't
cross-platform.  Additionally, using a series of ``subprocess.Popen`` calls was
leading to path-related issues for some users, even on "supported" platforms.

Newer version of ``Chroniker`` have attempted to solve this problem in the
following way:

    1.  Get a list of ``Job``\s that are "due"
    2.  For each ``Job``, launch a ``multiprocessing.Process`` instance, which
        internally calls ``django.core.management.call_command``
    3.  When the ``Job`` is run, we spawn a ``threading.Thread`` instance whose
        sole purpose is to keep track of a lock file.  This thread exists only
        while the Job is running and updates the file every second.  We store
        the path to this temporary file (an instance of
        ``tempfile.NamedTemporaryFile``) on the ``Job`` model (which is then
        stored in the database).  When we want to check if a ``Job`` is running
        we do the following:
        
        1.  If ``is_running`` equals ``True``, and ``lock_file`` point to a
            file, then:
            
            1.  If the lock file actually exists and has been updated more
                recently than ``CHRONIKER_LOCK_TIMEOUT`` seconds, then we
                can assume that the ``Job`` is still running
        2.  Else we assume the ``Job`` is not running and update the database
            accordingly

This new method should would much more reliably across all platforms that
support the threading and multiprocess libraries.

Development
-----------

To run unittests across multiple Python versions, install:

    sudo add-apt-repository ppa:deadsnakes/ppa
    sudo apt-get update
    sudo apt-get install python-dev python3-dev python3.3-minimal python3.3-dev python3.4-minimal python3.4-dev python3.5-minimal python3.5-dev python3.6 python3.6-dev

To run all [tests](http://tox.readthedocs.org/en/latest/):

    export TESTNAME=; tox

To run tests for a specific environment (e.g. Python 2.7 with Django 1.11):
    
    export TESTNAME=; tox -e py27-django111

To run a specific test:
    
    export TESTNAME=.testTimezone2; tox -e py36-django21

To run the [documentation server](http://www.mkdocs.org/#getting-started) locally:

    mkdocs serve -a :9999

To [deploy documentation](http://www.mkdocs.org/user-guide/deploying-your-docs/), run:

    mkdocs gh-deploy --clean

To build and deploy a versioned package to PyPI, verify [all unittests are passing](https://travis-ci.org/chrisspen/django-chroniker), and then run:

    python setup.py sdist
    python setup.py sdist upload

To commit while skipping the pre-commit hooks:

    SKIP=yapf git commit -m "foo"
