
from django.conf.urls import patterns, url, include
from django.contrib import admin

admin.autodiscover()

urlpatterns = patterns('chroniker.tests.views',
    url(r'^admin/', include(admin.site.urls)),
)
