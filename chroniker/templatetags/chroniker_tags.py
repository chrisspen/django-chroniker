from django import template
from django.core.urlresolvers import reverse, NoReverseMatch
from django.utils import timezone
from django.conf import settings

register = template.Library()

class RunJobURLNode(template.Node):
    def __init__(self, object_id):
        self.object_id = template.Variable(object_id)

    def render(self, context):
        object_id = self.object_id.resolve(context)
        try:
            # Old way
            url = reverse('chroniker_job_run', args=(object_id,))
        except NoReverseMatch:
            # New way
            url = reverse('admin:chroniker_job_run', args=(object_id,))
        return url

def do_get_run_job_url(parser, token):
    """
    Returns the URL to the view that does the 'run_job' command.

    Usage::

        {% get_run_job_url [object_id] %}
    """
    try:
        # Splitting by None == splitting by spaces.
        tag_name, object_id = token.contents.split(None, 1)
    except ValueError:
        raise template.TemplateSyntaxError(
            "%r tag requires one argument" % token.contents.split()[0])
    return RunJobURLNode(object_id)

register.tag('get_run_job_url', do_get_run_job_url)

@register.simple_tag
def now_offset(format_string, offset_days=0):
    """
    Like Django's built-in {% now ... %} tag, except it accepts a second
    integer parameter representing days to add to the current datetime.
    """
    from django.template.defaultfilters import date
    from datetime import datetime, timedelta
    offset_days = int(offset_days)
    tzinfo = timezone.get_current_timezone() if settings.USE_TZ else None
    dt = datetime.now(tz=tzinfo) + timedelta(days=offset_days)
    return date(dt, format_string)
