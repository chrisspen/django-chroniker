
from django.conf.urls import *
from django.contrib import admin

admin.autodiscover()

urlpatterns = patterns('chroniker.tests.views',
    (r'^admin/', include(admin.site.urls)),
)
