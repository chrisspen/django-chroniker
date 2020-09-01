from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect, get_object_or_404

from chroniker.admin import JobAdmin
from chroniker.models import Job, Log


def job_run(request, pk):
    return JobAdmin(Job, admin.site).run_job_view(request, pk)


job_run = user_passes_test(lambda user: user.is_superuser)(job_run)


CTX = {'site_name': settings.CHRONIKER_SITE_NAME}


def jobs(request):
    """Displays a list of jobs in a user facing UI"""
    CTX['jobs'] = Job.objects.all().order_by('name', '-enabled')
    return render(request, 'jobs/jobs.html', CTX)


def job(request, pk, run=False, last_run=False, toggle=False):
    """Show a job page with latest logs and buttons to force run and turn on/off"""
    j = get_object_or_404(Job, pk=pk)
    if run:
        j.force_run = True
        j.save()
        messages.success(request, 'job was now set to run this next minute')
    if toggle:
        j.enabled = not j.enabled
        j.save()
        return redirect('job', j.pk)
    if last_run:
        last_log = Log.objects.filter(job=j).order_by('pk').last()
        if last_log:
            return redirect('job_log', last_log.pk)
    CTX['job'] = j
    limit = 30
    CTX['logs'] = j.logs.order_by('-pk')[:limit]
    CTX['limit'] = limit
    return render(request, 'jobs/job.html', CTX)


def log(request, pk):
    """Show a log page"""
    CTX['log'] = get_object_or_404(Log, pk=pk)
    return render(request, 'jobs/log.html', CTX)
