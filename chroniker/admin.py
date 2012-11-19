
from datetime import datetime

from django import forms
from django.conf.urls.defaults import patterns, url
from django.contrib import admin
from django.core.management import get_commands
from django.core.urlresolvers import reverse, NoReverseMatch
from django.db import models
from django.forms import TextInput
from django.forms.util import flatatt
from django.http import HttpResponseRedirect, Http404
from django.template.defaultfilters import linebreaks
from django.utils import dateformat, timezone
from django.utils.datastructures import MultiValueDict
from django.utils.formats import get_format
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.translation import (
    ungettext,
    ugettext_lazy as _
)

from chroniker.models import Job, Log, JobDependency, Monitor
from chroniker.utils import get_admin_changelist_url
from chroniker.widgets import ImproveRawIdFieldsFormTabularInline

class HTMLWidget(forms.Widget):
    def __init__(self,rel=None, attrs=None):
        self.rel = rel
        super(HTMLWidget, self).__init__(attrs)
    
    def render(self, name, value, attrs=None):
        if self.rel is not None:
            key = self.rel.get_related_field().name
            obj = self.rel.to._default_manager.get(**{key: value})
            related_url = '../../../%s/%s/%d/' % (
                self.rel.to._meta.app_label,
                self.rel.to._meta.object_name.lower(),
                value)
            value = "<a href='%s'>%s</a>" % (related_url, escape(obj))
            
        final_attrs = self.build_attrs(attrs, name=name)
        return mark_safe("<div%s>%s</div>" % (
            flatatt(final_attrs),
            linebreaks(value)))

class JobDependencyInline(ImproveRawIdFieldsFormTabularInline):
    model = JobDependency
    extra = 1
    fk_name = 'dependent'
    
    readonly_fields = (
        'criteria_met',
    )
    
    raw_id_fields = (
        'dependee',
    )

class JobAdmin(admin.ModelAdmin):
    
    formfield_overrides = {
        models.CharField: {
            'widget': TextInput(attrs={'size':'100',})
        },
    }
    
    actions = (
        'run_selected_jobs',
        'toggle_enabled',
    )
    list_display = (
        'name',
        'last_run_with_link',
        'get_timeuntil',
        'get_frequency',
        'enabled',
        #'check_is_running',
        'check_is_complete',
        'is_fresh',
        'last_run_successful',
        'progress_percent_str',
        'estimated_completion_datetime_str',
        'run_button',
        'stop_button',
        'view_logs_button',
    )
    readonly_fields = (
        'check_is_running',
        'check_is_complete',
        'view_logs_button',
        'last_run_successful',
        'last_heartbeat',
        'is_fresh',
        'last_run_start_timestamp',
        'last_run',
        'total_parts',
        'total_parts_complete',
        'progress_percent_str',
        'estimated_completion_datetime_str',
    )
    list_display_links = ('name', )
    list_filter = (
        'frequency',
        'enabled',
        'hostname',
    )
    filter_horizontal = ('subscribers',)
    fieldsets = (
        ('Job Details', {
            'classes': ('wide',),
            'fields': (
                'name',
                'command',
                'args',
                'hostname',
                'enabled',
                'check_is_running',
                'force_run',
                'force_stop',
                'view_logs_button',
                'last_run_successful',
                'last_heartbeat',
                'is_fresh',
                'last_run_start_timestamp',
                'last_run',
                'total_parts',
                'total_parts_complete',
                'progress_percent_str',
                'estimated_completion_datetime_str',
                'is_monitor',
                'monitor_url',
            )
        }),
        ('E-mail subscriptions', {
            'classes': ('wide',),
            'fields': (
                'subscribers',
                'email_errors_to_subscribers',
                'email_success_to_subscribers',
            )
        }),
        ('Frequency options', {
            'classes': ('wide',),
            'fields': ('frequency', 'next_run', 'params',)
        }),
    )
    search_fields = ('name', )
    
    inlines = (
       JobDependencyInline,
    )
    
    def last_run_with_link(self, obj):
        format = get_format('DATETIME_FORMAT')
        value = capfirst(dateformat.format(timezone.localtime(obj.last_run), format))
        
        try:
            log_id = obj.log_set.latest('run_start_datetime').id
            try:
                # Old way
                url = reverse('chroniker_log_change', args=(log_id,))
            except NoReverseMatch:
                # New way
                url = reverse('admin:chroniker_log_change', args=(log_id,))
            return '<a href="%s">%s</a>' % (url, value)
        except:
            return value
    last_run_with_link.admin_order_field = 'last_run'
    last_run_with_link.allow_tags = True
    last_run_with_link.short_description = 'Last run'
    
    def check_is_complete(self, obj):
        return not obj.check_is_running()
    check_is_complete.short_description = _('is complete')
    check_is_complete.boolean = True
    
    def get_timeuntil(self, obj):
        format = get_format('DATETIME_FORMAT')
        value = capfirst(dateformat.format(timezone.localtime(obj.next_run), format))
        return "%s<br /><span class='mini'>(%s)</span>" \
            % (value, obj.get_timeuntil())
    get_timeuntil.admin_order_field = 'next_run'
    get_timeuntil.allow_tags = True
    get_timeuntil.short_description = _('next scheduled run')
    
    def get_frequency(self, obj):
        freq = capfirst(obj.frequency.lower())
        if obj.params:
            return "%s (%s)" % (freq, obj.params)
        return freq
    get_frequency.admin_order_field = 'frequency'
    get_frequency.short_description = 'Frequency'
    
    def run_button(self, obj):
        url = '%d/run/?inline=1' % obj.id
        return '<a href="%s"><input type="button" value="Run" /></a>' % url
    run_button.allow_tags = True
    run_button.short_description = 'Run'
    
    def stop_button(self, obj):
        url = '%d/stop/?inline=1' % obj.id
        vars = dict(url=url, disabled='')
        if not obj.is_running:
            vars['disabled'] = 'disabled'
        s = ('<a href="%(url)s"><input type="button" %(disabled)s ' + \
            'value="Stop" /></a>') % vars
        return s
    stop_button.allow_tags = True
    stop_button.short_description = 'Stop'
    
    def view_logs_button(self, obj):
        q = obj.logs.all()
        url = get_admin_changelist_url(Log)
        return ('<a href="%s?job=%d" target="_blank">'
            '<input type="button" value="View %i" /></a>') % \
            (url, obj.id, q.count())
    view_logs_button.allow_tags = True
    view_logs_button.short_description = 'Logs'
    
    def run_job_view(self, request, pk):
        """
        Runs the specified job.
        """
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            raise Http404
        # Rather than actually running the Job right now, we
        # simply force the Job to be run by the next cron job
        job.force_run = True
        job.save()
        self.message_user(
            request,
            _('The job "%(job)s" has been scheduled to run.') \
                % {'job': job})
        if 'inline' in request.GET:
            redirect = request.path + '../../'
        else:
            redirect = request.REQUEST.get('next', request.path + "../")
        return HttpResponseRedirect(redirect)
    
    def stop_job_view(self, request, pk):
        """
        Stop the specified job.
        """
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            raise Http404
        # Rather than actually running the Job right now, we
        # simply force the Job to be run by the next cron job
        job.force_run = False
        job.force_stop = True
        job.save()
        self.message_user(
            request,
            _('The job "%(job)s" is being signalled to stop.') \
                % {'job': job})
        if 'inline' in request.GET:
            redirect = request.path + '../../'
        else:
            redirect = request.REQUEST.get('next', request.path + "../")
        return HttpResponseRedirect(redirect)
    
    def get_urls(self):
        urls = super(JobAdmin, self).get_urls()
        my_urls = patterns('',
            url(r'^(.+)/run/$',
                self.admin_site.admin_view(self.run_job_view),
                name="chroniker_job_run"),
            url(r'^(.+)/stop/$',
                self.admin_site.admin_view(self.stop_job_view),
                name="chroniker_job_stop"),
        )
        return my_urls + urls
    
    def run_selected_jobs(self, request, queryset):
        rows_updated = queryset.update(next_run=timezone.now())
        if rows_updated == 1:
            message_bit = "1 job was"
        else:
            message_bit = "%s jobs were" % rows_updated
        self.message_user(request, "%s successfully set to run." % message_bit)
    run_selected_jobs.short_description = "Run selected jobs"
    
    def toggle_enabled(self, request, queryset):
        for row in queryset:
            row.enabled = not row.enabled
            row.save()
        rows_updated = queryset.count()
        if rows_updated == 1:
            message_bit = "1 job was toggled"
        else:
            message_bit = "%s jobs were toggled" % rows_updated
        self.message_user(request, message_bit)
    toggle_enabled.short_description = "Toggle enabled flag on selected jobs"
    
    def formfield_for_dbfield(self, db_field, **kwargs):
        request = kwargs.pop("request", None)
        
        # Add a select field of available commands
        if db_field.name == 'command':
            choices_dict = MultiValueDict()
            for command, app in get_commands().items():
                choices_dict.appendlist(app, command)
            
            choices = []
            for key in choices_dict.keys():
                #if str(key).startswith('<'):
                #    key = str(key)
                commands = choices_dict.getlist(key)
                commands.sort()
                choices.append([key, [[c,c] for c in commands]])
                
            kwargs['widget'] = forms.widgets.Select(choices=choices)
            return db_field.formfield(**kwargs)
        
        kwargs['request'] = request
        return super(JobAdmin, self).formfield_for_dbfield(db_field, **kwargs)

class LogAdmin(admin.ModelAdmin):
    list_display = (
        'job_name',
        'run_start_datetime',
        'run_end_datetime',
        'duration_seconds',
        'duration_str',
        'job_success',
        #'stdout_sample',
        #'stderr_sample',
    )
    search_fields = (
        'stdout',
        'stderr',
        'job__name',
        'job__command',
    )
    readonly_fields = (
        'run_start_datetime',
        'run_end_datetime',
        'duration_seconds',
        'stdout_long_sample',
        'stderr_long_sample',
        'stdout_link',
        'stderr_link',
        'duration_str',
    )
    date_hierarchy = 'run_start_datetime'
    fieldsets = (
        (None, {
            'fields': (
                'job',
                'run_start_datetime',
                'run_end_datetime',
                'duration_seconds',
                'duration_str',
            )
        }),
        ('Output', {
            'fields': (
                'stderr_link',
                'stderr_long_sample',
                'stdout_link',
                'stdout_long_sample',
            )
        }),
    )
    
    def stdout_link(self, obj):
        url = reverse("admin:chroniker_log_change", args=(obj.id,)) + 'stdout/'
        return '<a href="%s">Download</a>' % (url,)
    stdout_link.allow_tags = True
    stdout_link.short_description = 'Stdout full'
    
    def stderr_link(self, obj):
        url = reverse("admin:chroniker_log_change", args=(obj.id,)) + 'stderr/'
        return '<a href="%s">Download</a>' % (url,)
    stderr_link.allow_tags = True
    stderr_link.short_description = 'Stderr full'
    
    def view_full_stdout(self, request, log_id):
        from django.http import HttpResponse
        log = Log.objects.get(id=log_id)
        resp = HttpResponse(
            log.stdout,
            mimetype='application/x-download',
        )
        resp['Content-Disposition'] = 'filename=log-%s-stdout.txt' % (log_id,)
        return resp
    
    def view_full_stderr(self, request, log_id):
        from django.http import HttpResponse
        log = Log.objects.get(id=log_id)
        resp = HttpResponse(
            log.stderr,
            mimetype='application/x-download',
        )
        resp['Content-Disposition'] = 'filename=log-%s-stderr.txt' % (log_id,)
        return resp
    
    def get_urls(self):
        from django.conf.urls.defaults import *
        urls = super(LogAdmin, self).get_urls()
        my_urls = patterns('',
            (r'^(?P<log_id>[0-9]+)/stdout/?$',
                self.admin_site.admin_view(self.view_full_stdout)),
            (r'^(?P<log_id>[0-9]+)/stderr/?$',
                self.admin_site.admin_view(self.view_full_stderr)),
        )
        return my_urls + urls
    
    def job_name(self, obj):
      return obj.job.name
    job_name.short_description = _(u'Name')

    def job_success(self, obj):
            return obj.success
    job_success.short_description = _(u'OK')
    job_success.boolean = True
    
    def has_add_permission(self, request):
        return False
    
    def formfield_for_dbfield(self, db_field, **kwargs):
        request = kwargs.pop("request", None)
        
        if isinstance(db_field, models.TextField):
            kwargs['widget'] = HTMLWidget()
            return db_field.formfield(**kwargs)
        
        if isinstance(db_field, models.ForeignKey):
            kwargs['widget'] = HTMLWidget(db_field.rel)
            return db_field.formfield(**kwargs)
        
        return super(LogAdmin, self).formfield_for_dbfield(db_field, **kwargs)

try:
    admin.site.register(Job, JobAdmin)
except admin.sites.AlreadyRegistered:
    pass

admin.site.register(Log, LogAdmin)

class MonitorAdmin(admin.ModelAdmin):
    list_display = (
        'name_str',
        'status',
        'get_timeuntil',
        'enabled',
        'action_buttons',
    )
    list_filter = (
        'last_run_successful',
    )
    readonly_fields = (
        'name_str',
        'action_buttons',
        'status',
        'get_timeuntil',
    )
    
    def get_timeuntil(self, obj):
        format = get_format('DATETIME_FORMAT')
        value = capfirst(dateformat.format(timezone.localtime(obj.next_run), format))
        return "%s<br /><span class='mini'>(%s)</span>" \
            % (value, obj.get_timeuntil())
    get_timeuntil.admin_order_field = 'next_run'
    get_timeuntil.allow_tags = True
    get_timeuntil.short_description = _('next check')
    
    def get_actions(self, request):
        actions = super(MonitorAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_add_permission(self, request):
        return False 
    
    def queryset(self, request):
        qs = super(MonitorAdmin, self).queryset(request)
        qs = qs.filter(is_monitor=True)
        qs = qs.order_by('name')
        return qs
    
    def name_str(self, obj):
        if obj.monitor_url:
            from django.template import Context, Template
            from django.template.loader import render_to_string
            t = Template('{% load chronograph_tags %}' + obj.monitor_url)
            c = Context(dict(
                #date=timezone.now(),#.strftime('%Y-%m-%d'),
            ))
            url = t.render(c)
            return '<a href="%s" target="_blank">%s</a>' % (url, obj.name)
        else:
            return obj.name
    name_str.short_description = 'Name'
    name_str.allow_tags = True
    
    def action_buttons(self, obj):
        buttons = []
        url = '%d/run/?inline=1' % obj.id
        buttons.append('<a href="%s"><input type="button" value="Check now" /></a>' % url)
        buttons.append('<a href="/admin/chroniker/job/%i/" target="_blank"><input type="button" value="Edit" /></a>' % (obj.id,))
        return ' '.join(buttons)
    action_buttons.allow_tags = True
    action_buttons.short_description = 'Actions'
    
    def status(self, obj):
        if obj.is_running:
            help_text = 'The monitor is currently being checked.'
            temp = '<img src="/media/admin/img/icon-unknown.gif" alt="%(help_text)s" title="%(help_text)s" />'
        elif obj.last_run_successful:
            help_text = 'All checks passed.'
            temp = '<img src="/media/admin/img/icon_success.gif" alt="%(help_text)s" title="%(help_text)s" />'
        else:
            help_text = 'Requires attention.'
            temp = '<img src="/media/admin/img/icon_error.gif" alt="%(help_text)s" title="%(help_text)s" />'
        return temp % dict(help_text=help_text)
            
    status.allow_tags = True

    def changelist_view(self, request, extra_context=None):
        return super(MonitorAdmin, self).changelist_view(
            request, extra_context=dict(title='View monitors'))

    def run_job_view(self, request, pk):
        """
        Runs the specified job.
        """
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            raise Http404
        # Rather than actually running the Job right now, we
        # simply force the Job to be run by the next cron job
        job.force_run = True
        job.save()
        self.message_user(
            request,
            _('The monitor "%(job)s" will be checked.') \
                % {'job': job})
        if 'inline' in request.GET:
            redirect = request.path + '../../'
        else:
            redirect = request.REQUEST.get('next', request.path + "../")
        return HttpResponseRedirect(redirect)
    
    def get_urls(self):
        urls = super(MonitorAdmin, self).get_urls()
        my_urls = patterns('',
            url(r'^(.+)/run/$',
                self.admin_site.admin_view(self.run_job_view),
                name="chroniker_job_run"),
#            url(r'^(.+)/stop/$',
#                self.admin_site.admin_view(self.stop_job_view),
#                name="chroniker_job_stop"),
        )
        return my_urls + urls

admin.site.register(Monitor, MonitorAdmin)
