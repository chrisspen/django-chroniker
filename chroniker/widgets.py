from django.contrib import admin
from django.contrib.admin.sites import site
from django.contrib.admin.widgets import ManyToManyRawIdWidget, ForeignKeyRawIdWidget
from django.urls import reverse
from django.utils.encoding import smart_str
from django.utils.html import escape

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
                x = smart_str(obj)
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
