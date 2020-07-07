from django.contrib import admin
from django.contrib.admin.sites import site
from django.contrib.admin.widgets import ManyToManyRawIdWidget, ForeignKeyRawIdWidget
from django.forms.widgets import Select, TextInput
try:
    from django.forms.widgets import flatatt
except ImportError:
    from django.forms.utils import flatatt
from django.template import Context, Template
from django.urls import reverse
try:
    # force_unicode was deprecated in Django 1.5.
    from django.utils.encoding import force_unicode as force_text
    from django.utils.encoding import smart_unicode as smart_text
except ImportError:
    from django.utils.encoding import force_text
    from django.utils.encoding import smart_text
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .utils import get_admin_change_url, get_admin_changelist_url


class LinkedSelect(Select):

    def render(self, name, value, attrs=None, renderer=None):
        output = super().render(name, value, attrs=attrs, renderer=renderer)
        model = self.choices.field.queryset.model
        to_field_name = self.choices.field.to_field_name or 'id'
        try:
            kwargs = {to_field_name: value}
            obj = model.objects.get(**kwargs)
            view_url = get_admin_change_url(obj)
            output += mark_safe('&nbsp;<a href="%s" target="_blank">view</a>&nbsp;' % (view_url,))
        except model.DoesNotExist:
            pass
        return output


class ForeignKeyTextInput(TextInput):
    """
    Implements the same markup as VerboseForeignKeyRawIdWidget but does not
    require an explicit model relationship.
    """

    def __init__(self, model_class, value, *args, **kwargs):
        super(ForeignKeyTextInput, self).__init__(*args, **kwargs)
        self._model_class = model_class
        self._raw_value = value
        q = model_class.objects.filter(id=value)
        self._instance = None
        if q.count():
            self._instance = q[0]

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = ''
        final_attrs = self.build_attrs(attrs, extra_attrs={'type': self.input_type, 'name': name})
        if value != '':
            # Only add the 'value' attribute if a value is non-empty.
            final_attrs['value'] = force_text(self._format_value(value))
        final_attrs['size'] = 10
        t = Template(
            str(
                """
{% load staticfiles %}
<input{{ attrs|safe }} />
{% if instance %}
    <a href="{{ changelist_url|safe }}?t=id" class="related-lookup" id="lookup_{{ id|safe }}" onclick="return showRelatedObjectLookupPopup(this);">
        <img src="{% static 'admin/img/selector-search.gif' %}" width="16" height="16" alt="Lookup" />
    </a>
    <strong><a href="{{ url|safe }}" target="_blank">{{ instance|safe }}</a></strong>
{% endif %}
        """
            )
        )
        c = Context(
            dict(
                id=final_attrs['id'],
                attrs=flatatt(final_attrs),
                raw_value=self._raw_value,
                url=get_admin_change_url(self._instance),
                changelist_url=get_admin_changelist_url(self._model_class),
                instance=self._instance
            )
        )
        return mark_safe(t.render(c))


#http://djangosnippets.org/snippets/2217/


class VerboseForeignKeyRawIdWidget(ForeignKeyRawIdWidget):

    def label_for_value(self, value):
        key = self.remote_field.get_related_field().name
        try:
            obj = self.remote_field.model._default_manager.using(self.db).get(**{key: value})
            change_url = reverse("admin:%s_%s_change" % (obj._meta.app_label, obj._meta.object_name.lower()), args=(obj.pk,))
            return '&nbsp;<strong><a href="%s" target="_blank">%s</a></strong>' \
                % (change_url, escape(obj))
        except (ValueError, self.remote_field.model.DoesNotExist):
            return ''


class VerboseManyToManyRawIdWidget(ManyToManyRawIdWidget):

    def label_for_value(self, value):
        values = value.split(',')
        str_values = []
        key = self.remote_field.get_related_field().name
        for v in values:
            try:
                obj = self.remote_field.model._default_manager.using(self.db).get(**{key: v})
                x = smart_text(obj)
                change_url = reverse("admin:%s_%s_change" % (obj._meta.app_label, obj._meta.object_name.lower()), args=(obj.pk,))
                str_values += ['<strong><a href="%s" target="_blank">%s</a></strong>' \
                    % (change_url, escape(x))]
            except self.remote_field.model.DoesNotExist:
                str_values += ['???']
        return ', '.join(str_values)


class ImproveRawIdFieldsForm(admin.ModelAdmin):

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in self.raw_id_fields:
            if hasattr(db_field, 'remote_field'):
                remote_field = db_field.remote_field
            else:
                remote_field = db_field.rel
            typ = remote_field.__class__.__name__
            if typ == 'ManyToOneRel':
                kwargs['widget'] = VerboseForeignKeyRawIdWidget(remote_field, site)
            elif typ == 'ManyToManyRel':
                kwargs['widget'] = VerboseManyToManyRawIdWidget(remote_field, site)
            return db_field.formfield(**kwargs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)


class ImproveRawIdFieldsFormTabularInline(admin.TabularInline):

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in self.raw_id_fields:
            if hasattr(db_field, 'remote_field'):
                remote_field = db_field.remote_field
            else:
                remote_field = db_field.rel
            typ = remote_field.__class__.__name__
            if typ == 'ManyToOneRel':
                kwargs['widget'] = VerboseForeignKeyRawIdWidget(remote_field, site)
            elif typ == 'ManyToManyRel':
                kwargs['widget'] = VerboseManyToManyRawIdWidget(remote_field, site)
            return db_field.formfield(**kwargs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)
