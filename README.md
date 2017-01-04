Chroniker - Django Controlled Cron Jobs
=============================================================================

[![](https://img.shields.io/pypi/v/django-chroniker.svg)](https://pypi.python.org/pypi/django-chroniker) [![Build Status](https://img.shields.io/travis/chrisspen/django-chroniker.svg?branch=master)](https://travis-ci.org/chrisspen/django-chroniker) [![](https://pyup.io/repos/github/chrisspen/django-chroniker/shield.svg)](https://pyup.io/repos/github/chrisspen/django-chroniker)

Overview
--------

Allows you to use cron to schedule Django management commands through
Django's admin.

Creating cron jobs for Django apps can be a pain, annoying and repetitive.
With django-chroniker you simply create a single cron job to run every minute,
point it at your site's directory and run `manage.py cron`.
Then, you can create, update and delete jobs through Django's admin.

This is a fork of Weston Nielson's [Chronograph](https://bitbucket.org/wnielson/django-chronograph/) project.

[Click here for documentation](http://chrisspen.github.io/django-chroniker/).
