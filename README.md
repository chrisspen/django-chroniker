Chroniker - Django Controlled Cron Jobs
=============================================================================

Overview
--------

Allows you to use cron to schedule Django management commands through
Django's admin.

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
    
Add 'chroniker' to the INSTALLED_APPS list in your settings.py.

If you're using South (which you should be), install Chroniker's models by running:

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
