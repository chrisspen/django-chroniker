from django import forms
from django.conf.urls.defaults import patterns, url
from django.contrib import admin
from django.core.management import get_commands
from django.core.urlresolvers import reverse, NoReverseMatch
from django.db import models
from django.forms.util import flatatt
from django.http import HttpResponseRedirect, Http404
from django.template.defaultfilters import linebreaks
from django.utils import dateformat
from django.utils.datastructures import MultiValueDict
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.translation import ungettext, get_date_formats, ugettext_lazy as _

from chroniker.models import Job, Log
from chroniker.utils import get_admin_changelist_url

from datetime import datetime

class HTMLWidget(forms.Widget):
    def __init__(self,rel=None, attrs=None):
        self.rel = rel
        super(HTMLWidget, self).__init__(attrs)
    
    def render(self, name, value, attrs=None):
        if self.rel is not None:
            key = self.rel.get_related_field().name
            obj = self.rel.to._default_manager.get(**{key: value})
            related_url = '../../../%s/%s/%d/' % (self.rel.to._meta.app_label, self.rel.to._meta.object_name.lower(), value)
            value = "<a href='%s'>%s</a>" % (related_url, escape(obj))
            
        final_attrs = self.build_attrs(attrs, name=name)
        return mark_safe("<div%s>%s</div>" % (flatatt(final_attrs), linebreaks(value)))

class JobAdmin(admin.ModelAdmin):
    actions = ['run_selected_jobs']
    list_display = (
        'name',
        'last_run_with_link',
        'get_timeuntil',
        'get_frequency',
        'disabled',
        'check_is_running',
        'run_button',
        'view_logs_button',
    )
    readonly_fields = (
        'check_is_running',
        'view_logs_button',
    )
    list_display_links = ('name', )
    list_filter = ('last_run_successful', 'frequency', 'disabled')
    filter_horizontal = ('subscribers',)
    fieldsets = (
        ('Job Details', {
            'classes': ('wide',),
            'fields': (
                'name',
                'command',
                'args',
                'disabled',
                'check_is_running',
                'force_run',
                'view_logs_button',
            )
        }),
        ('E-mail subscriptions', {
            'classes': ('wide',),
            'fields': ('subscribers',)
        }),
        ('Frequency options', {
            'classes': ('wide',),
            'fields': ('frequency', 'next_run', 'params',)
        }),
    )
    search_fields = ('name', )
    
    def last_run_with_link(self, obj):
        format = get_date_formats()[1]
        value = capfirst(dateformat.format(obj.last_run, format))
        
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
    
    def get_timeuntil(self, obj):
        format = get_date_formats()[1]
        value = capfirst(dateformat.format(obj.next_run, format))
        return "%s<br /><span class='mini'>(%s)</span>" % (value, obj.get_timeuntil())
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
        request.user.message_set.create(message=_('The job "%(job)s" has been scheduled to run.') % {'job': job})        
        if 'inline' in request.GET:
            redirect = request.path + '../../'
        else:
            redirect = request.REQUEST.get('next', request.path + "../")
        return HttpResponseRedirect(redirect)
    
    def get_urls(self):
        urls = super(JobAdmin, self).get_urls()
        my_urls = patterns('',
            url(r'^(.+)/run/$', self.admin_site.admin_view(self.run_job_view), name="chroniker_job_run")
        )
        return my_urls + urls
    
    def run_selected_jobs(self, request, queryset):
        rows_updated = queryset.update(next_run=datetime.now())
        if rows_updated == 1:
            message_bit = "1 job was"
        else:
            message_bit = "%s jobs were" % rows_updated
        self.message_user(request, "%s successfully set to run." % message_bit)
    run_selected_jobs.short_description = "Run selected jobs"
    
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
        'job_success',
        'output',
        'errors',
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
    )
    date_hierarchy = 'run_start_datetime'
    fieldsets = (
        (None, {
            'fields': (
                'job',
                'run_start_datetime',
                'run_end_datetime',
                'duration_seconds',
            )
        }),
        ('Output', {
            'fields': ('stdout', 'stderr',)
        }),
    )
    
    def job_name(self, obj):
      return obj.job.name
    job_name.short_description = _(u'Name')

    def job_success(self, obj):
            return obj.success
    job_success.short_description = _(u'OK')
    job_success.boolean = True

    def output(self, obj):
        result = obj.stdout or ''
        if len(result) > 40:
            result = result[:40] + '...'
        return result or '(No output)'

    def errors(self, obj):
        result = obj.stderr or ''
        if len(result) > 40:
            result = result[:40] + '...'
        return result or '(No errors)'
    
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